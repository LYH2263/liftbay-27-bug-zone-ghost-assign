from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Building, CallTicket, DispatchLog, ElevatorCar


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Building.id).limit(1)):
        return
    b = Building(name="研发中心 A 座", floors=18)
    db.add(b)
    db.flush()
    cars = [
        # 低区车：只停 1–6 层
        ElevatorCar(building_id=b.id, label="A1", floor=4, direction="up", load=5, capacity=10, floor_min=1, floor_max=6),
        ElevatorCar(building_id=b.id, label="A2", floor=12, direction="down", load=4, capacity=10, floor_min=12, floor_max=18),
        ElevatorCar(building_id=b.id, label="A3", floor=1, direction="idle", load=0, capacity=8, floor_min=1, floor_max=6),
        # 高区车：只停 12–18 层（A4 已满载）
        ElevatorCar(building_id=b.id, label="A4", floor=16, direction="idle", load=8, capacity=8, floor_min=12, floor_max=18),
    ]
    db.add_all(cars)
    db.flush()
    # 7–11 层为无覆盖空洞：这些层的呼梯登记会被直接拒绝
    c1 = CallTicket(building_id=b.id, floor=5, direction="up", passengers=2, status="waiting")
    c2 = CallTicket(building_id=b.id, floor=14, direction="down", passengers=1, status="waiting")
    c3 = CallTicket(
        building_id=b.id, floor=4, direction="up", passengers=3, status="assigned", assigned_car_id=cars[0].id, score="135.0"
    )
    db.add_all([c1, c2, c3])
    db.flush()
    db.add(DispatchLog(call_id=c3.id, car_id=cars[0].id, detail="同向优先派予 A1，评分 135.0"))
    db.commit()
