from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Building, CallTicket, DispatchLog, ElevatorCar
from app.schemas.schemas import (
    BuildingOut,
    CallCreate,
    CallOut,
    CarOut,
    CarRangeUpdate,
    CongestionFloor,
    DispatchRequest,
    LogOut,
)
from app.services.dispatch_engine import (
    CallRequest,
    CarState,
    any_coverage,
    congestion_by_floor,
    pick_car,
)

api_router = APIRouter()


def _car_states(rows) -> list[CarState]:
    return [
        CarState(c.id, c.floor, c.direction, c.load, c.capacity, c.floor_min, c.floor_max)
        for c in rows
    ]


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/buildings", response_model=list[BuildingOut])
def buildings(db: Session = Depends(get_db)):
    return db.scalars(select(Building).order_by(Building.id)).all()


@api_router.get("/cars", response_model=list[CarOut])
def cars(db: Session = Depends(get_db)):
    return db.scalars(select(ElevatorCar).order_by(ElevatorCar.id)).all()


@api_router.patch("/cars/{car_id}", response_model=CarOut)
def update_car_range(car_id: int, body: CarRangeUpdate, db: Session = Depends(get_db)):
    car = db.get(ElevatorCar, car_id)
    if not car:
        raise HTTPException(404, "轿厢不存在")
    if body.floor_min > body.floor_max:
        raise HTTPException(400, "区间下限不能大于上限")
    building = db.get(Building, car.building_id)
    if building and body.floor_max > building.floors:
        raise HTTPException(400, "区间超出楼栋楼层")
    car.floor_min = body.floor_min
    car.floor_max = body.floor_max
    db.commit()
    db.refresh(car)
    return car


@api_router.get("/calls", response_model=list[CallOut])
def calls(db: Session = Depends(get_db)):
    return db.scalars(select(CallTicket).order_by(CallTicket.id.desc())).all()


@api_router.post("/calls", response_model=CallOut)
def create_call(body: CallCreate, db: Session = Depends(get_db)):
    b = db.get(Building, body.building_id)
    if not b:
        raise HTTPException(404, "楼栋不存在")
    if body.floor > b.floors:
        raise HTTPException(400, "楼层超出")
    if body.direction not in ("up", "down"):
        raise HTTPException(400, "方向无效")
    ticket = CallTicket(
        building_id=body.building_id,
        floor=body.floor,
        direction=body.direction,
        passengers=body.passengers,
    )
    car_rows = db.scalars(
        select(ElevatorCar).where(ElevatorCar.building_id == body.building_id)
    ).all()
    if not any_coverage(_car_states(car_rows), body.floor):
        # 登记端只判覆盖（与载客无关）：无覆盖层不进 waiting，
        # 留 rejected 记录并写回放，原因与派工端的满员拒派分开
        ticket.status = "rejected"
        db.add(ticket)
        db.flush()
        detail = "本楼无轿厢覆盖该候梯层，拒绝登记"
        db.add(DispatchLog(call_id=ticket.id, car_id=None, detail=detail))
        db.commit()
        raise HTTPException(409, detail)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@api_router.post("/dispatch", response_model=CallOut)
def dispatch(body: DispatchRequest, db: Session = Depends(get_db)):
    ticket = db.get(CallTicket, body.call_id)
    if not ticket:
        raise HTTPException(404, "呼梯不存在")
    if ticket.status != "waiting":
        raise HTTPException(400, "呼梯已处理")
    car_rows = db.scalars(
        select(ElevatorCar).where(ElevatorCar.building_id == ticket.building_id)
    ).all()
    cars = _car_states(car_rows)
    call = CallRequest(ticket.id, ticket.floor, ticket.direction, ticket.passengers)
    best = pick_car(cars, call)
    if best is None:
        if any_coverage(cars, ticket.floor):
            detail = "覆盖该层的轿厢均满员，拒绝派工"
        else:
            detail = "本楼无轿厢覆盖该候梯层，拒绝派工"
        db.add(DispatchLog(call_id=ticket.id, car_id=None, detail=detail))
        ticket.status = "rejected"
        db.commit()
        db.refresh(ticket)
        raise HTTPException(409, detail)
    car = db.get(ElevatorCar, best.car_id)
    assert car
    ticket.status = "assigned"
    ticket.assigned_car_id = car.id
    ticket.score = f"{best.score:.1f}"
    car.load += ticket.passengers
    car.floor = ticket.floor
    car.direction = ticket.direction
    db.add(
        DispatchLog(
            call_id=ticket.id,
            car_id=car.id,
            detail=f"派予 {car.label}，评分 {best.score:.1f}（同向/距离综合）",
        )
    )
    db.commit()
    db.refresh(ticket)
    return ticket


@api_router.get("/replay", response_model=list[LogOut])
def replay(db: Session = Depends(get_db)):
    return db.scalars(select(DispatchLog).order_by(DispatchLog.id.desc())).all()


@api_router.get("/congestion", response_model=list[CongestionFloor])
def congestion(db: Session = Depends(get_db)):
    waiting = db.scalars(select(CallTicket).where(CallTicket.status == "waiting")).all()
    car_rows = db.scalars(select(ElevatorCar)).all()
    cars_by_building: dict[int, list[CarState]] = {}
    for row in car_rows:
        cars_by_building.setdefault(row.building_id, []).append(
            CarState(
                row.id, row.floor, row.direction, row.load, row.capacity,
                row.floor_min, row.floor_max,
            )
        )
    # 只统计仍占用现场的有效呼梯：waiting 且当前仍有轿厢覆盖该层
    active = [
        c for c in waiting
        if any_coverage(cars_by_building.get(c.building_id, []), c.floor)
    ]
    counts = congestion_by_floor(
        [CallRequest(c.id, c.floor, c.direction, c.passengers) for c in active]
    )
    return [
        CongestionFloor(floor=f, passengers=p)
        for f, p in sorted(counts.items(), key=lambda x: -x[1])
    ]
