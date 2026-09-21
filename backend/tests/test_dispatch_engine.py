from app.services.dispatch_engine import (
    CallRequest,
    CarState,
    any_coverage,
    pick_car,
    score_car,
)


def test_reject_when_full():
    car = CarState(1, 5, "idle", load=8, capacity=8)
    call = CallRequest(1, 5, "up", passengers=1)
    r = score_car(car, call)
    assert r.accepted is False
    assert "满员" in r.reason


def test_same_direction_beats_far_idle():
    cars = [
        CarState(1, 2, "up", load=1, capacity=10),
        CarState(2, 12, "idle", load=0, capacity=10),
    ]
    call = CallRequest(9, 4, "up", 1)
    best = pick_car(cars, call)
    assert best is not None
    assert best.car_id == 1


def test_closer_idle_wins_when_opposite():
    cars = [
        CarState(1, 10, "down", load=0, capacity=10),
        CarState(2, 3, "idle", load=0, capacity=10),
    ]
    call = CallRequest(3, 2, "up", 1)
    best = pick_car(cars, call)
    assert best is not None
    assert best.car_id == 2


def test_out_of_range_top_scorer_skipped():
    """区间外最高分车被跳过：同层 idle 车本可拿最高分，但够不到该层。"""
    cars = [
        CarState(1, 5, "idle", load=0, capacity=10, floor_min=7, floor_max=18),
        CarState(2, 2, "idle", load=0, capacity=10, floor_min=1, floor_max=6),
    ]
    call = CallRequest(1, 5, "up", 1)
    # 不设区间时 1 号车分数更高（120 > 105）
    r1 = score_car(cars[0], call)
    assert r1.accepted is False
    assert "区间" in r1.reason
    best = pick_car(cars, call)
    assert best is not None
    assert best.car_id == 2


def test_no_coverage_at_all():
    """全无覆盖层：any_coverage 为 False，pick_car 返回 None（登记端据此拒绝）。"""
    cars = [
        CarState(1, 3, "up", load=0, capacity=10, floor_min=1, floor_max=6),
        CarState(2, 12, "down", load=0, capacity=10, floor_min=12, floor_max=18),
    ]
    assert any_coverage(cars, 5) is True
    assert any_coverage(cars, 14) is True
    assert any_coverage(cars, 9) is False
    assert pick_car(cars, CallRequest(1, 9, "up", 1)) is None


def test_full_rejection_still_applies_within_range():
    """满员拒绝仍在候选集合内生效：区间内满员车被跳过，空车胜出。"""
    cars = [
        CarState(1, 4, "idle", load=8, capacity=8, floor_min=1, floor_max=6),
        CarState(2, 1, "idle", load=0, capacity=8, floor_min=1, floor_max=6),
    ]
    best = pick_car(cars, CallRequest(1, 4, "up", 1))
    assert best is not None
    assert best.car_id == 2
