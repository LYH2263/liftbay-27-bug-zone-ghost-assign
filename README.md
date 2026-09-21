# LiftBay

电梯派梯：服务区间门控 + 同向优先与楼层距离评分，轿厢满员拒绝派工。

## 服务区间（高低区）

- 每台轿厢登记可停楼层区间 `[floor_min, floor_max]`，区间外的候梯呼梯不会派给该轿厢（即使同向/距离评分更高）。
- 呼梯登记时若本楼没有任何轿厢覆盖该候梯层，直接拒绝登记（409），留下 `rejected` 记录并写入回放说明，不会留下永远派不出去的 `waiting`。
- 轿厢页可维护每台车的区间（持久化，重进页面仍在），区间外楼层在井道中变暗；派工页待派列表标出覆盖该层的候选轿厢。
- 种子数据：A1/A3 只服务低区 1–6 层，A2/A4 只服务高区 12–18 层，7–11 层呼梯登记会被拒绝。

## 启动

```bash
docker compose up --build
```

> 若之前用旧版本建过数据卷，本次新增了 `elevator_cars.floor_min/floor_max` 列，请先 `docker compose down -v` 重建数据库。

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4200 |
| API | http://localhost:9200 |
| API 文档 | http://localhost:9200/docs |
| Postgres | localhost:5443 |

健康检查：`GET http://localhost:9200/api/health`

## 页面

- `/buildings` — 楼栋
- `/cars` — 轿厢
- `/calls` — 呼梯
- `/dispatch` — 派工
- `/replay` — 回放
- `/congestion` — 拥堵

## 使用说明

1. 查看楼栋与轿厢状态。
2. 在呼梯页登记请求，在派工页按评分分配轿厢。
3. 回放页查看派工轨迹，拥堵页查看高峰楼层。

## 开发与测试

```bash
docker compose exec api pytest -q
```
