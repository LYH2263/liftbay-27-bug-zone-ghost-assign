"""服务区间 API 级测例：登记拒绝 + 派工区间门控（sqlite 内存库，不依赖 Postgres）。"""

import os
import tempfile
from uuid import uuid4

_TMPDIR = tempfile.mkdtemp(prefix="liftbay-zones-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMPDIR}/zones.db"
os.environ["SEED_ON_EMPTY"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import Building, ElevatorCar  # noqa: E402


def _seed_zones() -> int:
    """一台低区车（1–6）、一台高区车（12–18），7–11 层无覆盖。

    H1 当前停在 4 层（例如区间刚被调小、车还没来得及归位），
    这样若无区间门控，它对 4 层呼梯的评分会高于 L1 —— 用来锁住
    “区间外最高分车被跳过”。
    """
    db = SessionLocal()
    try:
        b = Building(name=f"区间测试楼-{uuid4().hex[:8]}", floors=18)
        db.add(b)
        db.flush()
        db.add_all(
            [
                ElevatorCar(
                    building_id=b.id, label="L1", floor=1, direction="idle",
                    load=0, capacity=10, floor_min=1, floor_max=6,
                ),
                ElevatorCar(
                    building_id=b.id, label="H1", floor=4, direction="idle",
                    load=0, capacity=10, floor_min=12, floor_max=18,
                ),
            ]
        )
        db.commit()
        return b.id
    finally:
        db.close()


def test_uncovered_floor_registration_rejected():
    with TestClient(app) as client:
        bid = _seed_zones()

        # 中间层（9 层）无任何轿厢覆盖 → 直接拒绝登记
        r = client.post(
            "/api/calls",
            json={"building_id": bid, "floor": 9, "direction": "up", "passengers": 1},
        )
        assert r.status_code == 409

        # 不得留下 waiting 却永远派不出去的呼梯
        calls = client.get("/api/calls").json()
        floor9 = [c for c in calls if c["floor"] == 9]
        assert floor9, "应留下 rejected 记录而不是静默丢弃"
        assert all(c["status"] == "rejected" for c in floor9)

        # 回放中有拒绝说明
        logs = client.get("/api/replay").json()
        assert any("无轿厢覆盖" in log["detail"] for log in logs)


def test_low_zone_call_never_goes_to_high_zone_car():
    with TestClient(app) as client:
        bid = _seed_zones()

        # 低区层登记成功
        r = client.post(
            "/api/calls",
            json={"building_id": bid, "floor": 4, "direction": "up", "passengers": 1},
        )
        assert r.status_code == 200
        call_id = r.json()["id"]

        # 派工：只能派给低区车 L1，即使高区车 H1 也是 idle
        r = client.post("/api/dispatch", json={"call_id": call_id})
        assert r.status_code == 200
        assigned_id = r.json()["assigned_car_id"]

        cars = {c["id"]: c for c in client.get("/api/cars").json()}
        assigned = cars[assigned_id]
        assert assigned["label"] == "L1"
        # 派工成功后当前楼层仍落在本车区间内
        assert assigned["floor_min"] <= assigned["floor"] <= assigned["floor_max"]


def test_update_car_range_persists():
    with TestClient(app) as client:
        bid = _seed_zones()
        car = next(
            c for c in client.get("/api/cars").json() if c["building_id"] == bid and c["label"] == "L1"
        )
        r = client.patch(f"/api/cars/{car['id']}", json={"floor_min": 2, "floor_max": 5})
        assert r.status_code == 200
        assert r.json()["floor_min"] == 2
        assert r.json()["floor_max"] == 5
        # 再次读取仍在（前端重进轿厢页能看到）
        again = client.get("/api/cars").json()
        car2 = next(c for c in again if c["id"] == car["id"])
        assert (car2["floor_min"], car2["floor_max"]) == (2, 5)

        # 下限大于上限 / 超出楼栋楼层 → 400
        assert client.patch(
            f"/api/cars/{car['id']}", json={"floor_min": 6, "floor_max": 3}
        ).status_code == 400
        assert client.patch(
            f"/api/cars/{car['id']}", json={"floor_min": 1, "floor_max": 99}
        ).status_code == 400
