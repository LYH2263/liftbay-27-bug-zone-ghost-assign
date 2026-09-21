import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
type Car = { id: number; label: string; floor: number; direction: string; load: number; capacity: number; floor_min: number; floor_max: number };
type Call = { id: number; floor: number; status: string };
type B = { floors: number };
type RangeDraft = { min: number; max: number };
export default function CarsPage() {
  const [cars, setCars] = useState<Car[]>([]);
  const [calls, setCalls] = useState<Call[]>([]);
  const [floors, setFloors] = useState(18);
  const [drafts, setDrafts] = useState<Record<number, RangeDraft>>({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const reloadCars = () => api<Car[]>("/cars").then(setCars);
  useEffect(() => {
    reloadCars();
    api<Call[]>("/calls").then(setCalls);
    api<B[]>("/buildings").then(bs => { if (bs[0]) setFloors(bs[0].floors); });
  }, []);
  // 与后端同一口径：只有本车服务区间覆盖到的 waiting 呼梯才在本井道标亮
  const callFloorsByCar = useMemo(() => {
    const byCar: Record<number, Set<number>> = {};
    for (const car of cars) {
      byCar[car.id] = new Set(
        calls
          .filter(c => c.status === "waiting" && car.floor_min <= c.floor && c.floor <= car.floor_max)
          .map(c => c.floor),
      );
    }
    return byCar;
  }, [cars, calls]);
  const levels = useMemo(() => Array.from({ length: floors }, (_, i) => i + 1), [floors]);
  async function saveRange(car: Car) {
    const d = drafts[car.id] ?? { min: car.floor_min, max: car.floor_max };
    setMsg(""); setErr("");
    if (d.min < 1 || d.max > floors || d.min > d.max) {
      setErr(`轿厢 ${car.label} 区间无效：需满足 1 ≤ 下限 ≤ 上限 ≤ ${floors}`);
      return;
    }
    try {
      await api(`/cars/${car.id}`, { method: "PATCH", body: JSON.stringify({ floor_min: d.min, floor_max: d.max }) });
      setMsg(`轿厢 ${car.label} 服务区间已更新为 ${d.min}–${d.max}`);
      setDrafts(prev => { const next = { ...prev }; delete next[car.id]; return next; });
      reloadCars();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  return (<>
    <h2>轿厢井道</h2>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    <div className="shaft-wrap">
      {cars.map(car => {
        const d = drafts[car.id] ?? { min: car.floor_min, max: car.floor_max };
        return (
          <div className="shaft-col" key={car.id}>
            <div className="shaft">
              <h3>{car.label} · {car.load}/{car.capacity}</h3>
              {levels.map(f => (
                <div key={f} className={`floor-slot ${car.floor === f ? "has-car" : ""} ${callFloorsByCar[car.id]?.has(f) ? "has-call" : ""} ${f < car.floor_min || f > car.floor_max ? "out-of-range" : ""}`}>
                  {car.floor === f ? car.direction : f}
                </div>
              ))}
            </div>
            <div className="range-editor">
              <span className="range-title">区间 {car.floor_min}–{car.floor_max}</span>
              <div className="range-inputs">
                <input type="number" min={1} max={floors} value={d.min}
                  onChange={e => setDrafts(p => ({ ...p, [car.id]: { ...d, min: Number(e.target.value) } }))} />
                <span>–</span>
                <input type="number" min={1} max={floors} value={d.max}
                  onChange={e => setDrafts(p => ({ ...p, [car.id]: { ...d, max: Number(e.target.value) } }))} />
              </div>
              <button onClick={() => saveRange(car)}>保存区间</button>
            </div>
          </div>
        );
      })}
    </div>
  </>);
}
