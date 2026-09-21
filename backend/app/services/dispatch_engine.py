"""Elevator dispatch: service-range gate first, then same-direction preference
+ floor distance scoring; reject if car full."""

from __future__ import annotations

from dataclasses import dataclass

#: 未显式登记区间时的默认上限（视为不限）
DEFAULT_FLOOR_MAX = 1_000_000


@dataclass(frozen=True)
class CarState:
    car_id: int
    floor: int
    direction: str  # "up" | "down" | "idle"
    load: int
    capacity: int
    floor_min: int = 1
    floor_max: int = DEFAULT_FLOOR_MAX


@dataclass(frozen=True)
class CallRequest:
    call_id: int
    floor: int
    direction: str  # desired travel after boarding
    passengers: int = 1


@dataclass(frozen=True)
class ScoreResult:
    car_id: int
    score: float
    accepted: bool
    reason: str


SAME_DIR_BONUS = 40.0
IDLE_BONUS = 20.0
DISTANCE_WEIGHT = 5.0


def covers_floor(car: CarState, floor: int) -> bool:
    """轿厢服务区间是否覆盖该楼层。"""
    return car.floor_min <= floor <= car.floor_max


def any_coverage(cars: list[CarState], floor: int) -> bool:
    """本楼是否有任意轿厢覆盖该候梯层（登记呼梯时的准入判断）。"""
    return any(covers_floor(c, floor) for c in cars)


def score_car(car: CarState, call: CallRequest) -> ScoreResult:
    if not covers_floor(car, call.floor):
        return ScoreResult(car.car_id, -1e9, False, "候梯层不在服务区间")
    if car.load + call.passengers > car.capacity:
        return ScoreResult(car.car_id, -1e9, False, "轿厢满员")

    distance = abs(car.floor - call.floor)
    score = 100.0 - distance * DISTANCE_WEIGHT

    if car.direction == "idle":
        score += IDLE_BONUS
    elif car.direction == call.direction:
        # approaching or already going same way
        if car.direction == "up" and car.floor <= call.floor:
            score += SAME_DIR_BONUS
        elif car.direction == "down" and car.floor >= call.floor:
            score += SAME_DIR_BONUS
        else:
            score -= 15.0  # same dir but already passed
    else:
        score -= 25.0

    return ScoreResult(car.car_id, score, True, "ok")


def pick_car(cars: list[CarState], call: CallRequest) -> ScoreResult | None:
    results = [score_car(c, call) for c in cars]
    accepted = [r for r in results if r.accepted]
    if not accepted:
        return None
    return max(accepted, key=lambda r: r.score)


def congestion_by_floor(calls: list[CallRequest]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for c in calls:
        counts[c.floor] = counts.get(c.floor, 0) + c.passengers
    return counts
