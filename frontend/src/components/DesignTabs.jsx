// DesignTabs.jsx - one tab per concept; inside each: floor plan tabs, room table, advantages, budget note.
import { useState } from "react";
import FloorPlanSVG from "./FloorPlanSVG.jsx";
import ImageGallery from "./ImageGallery.jsx";

const fmt = (n) => Number(n.toFixed(1));
const lakhs = (inr) => `₹${(inr / 100000).toFixed(1)} L`; // 1 lakh = 100,000 INR
const PARKING_NAMES = { two_wheeler: "Two-wheeler parking", "1_car": "Car parking", "2_cars": "Car parking (2 cars)" };

// Flat list of every room (and parking) for the dimensions table.
function roomRows(concept) {
  const rows = concept.floors.flatMap((f) =>
    f.rooms.map((r) => ({ floor: f.name, name: r.name, w: r.width, h: r.height }))
  );
  if (concept.parking) {
    const p = concept.parking;
    rows.push({ floor: "Ground Floor", name: PARKING_NAMES[p.type], w: p.width, h: p.height });
  }
  return rows;
}

function RoomTable({ concept }) {
  return (
    <table className="room-table">
      <thead>
        <tr><th>Floor</th><th>Room</th><th>Size (ft)</th><th>Area (sq ft)</th></tr>
      </thead>
      <tbody>
        {roomRows(concept).map((r) => (
          <tr key={`${r.floor}-${r.name}`}>
            <td>{r.floor}</td><td>{r.name}</td><td>{fmt(r.w)} x {fmt(r.h)}</td><td>{Math.round(r.w * r.h)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BudgetNote({ note, budget }) {
  return (
    <div className={`budget ${note.fits_budget ? "budget-ok" : "budget-over"}`}>
      <h4>Budget note (estimate)</h4>
      <p>
        About <strong>{lakhs(note.cost_min_inr)} to {lakhs(note.cost_max_inr)}</strong> for roughly {note.built_up_sqft} sq ft
        built-up area at ₹{note.rate_min_per_sqft} to ₹{note.rate_max_per_sqft} per sq ft.{" "}
        {note.fits_budget ? `This fits your budget of ${lakhs(budget)}.` : `This is above your budget of ${lakhs(budget)}.`}
      </p>
      {note.note && <p>{note.note}</p>}
      <p className="muted">{note.disclaimer}</p>
    </div>
  );
}

// Everything for one selected concept. The parent gives it a key so floor tabs reset per concept.
function DesignDetail({ design, request }) {
  const { concept } = design;
  const [floorIndex, setFloorIndex] = useState(0);
  const floor = concept.floors[floorIndex];

  return (
    <div className="design-detail">
      {design.is_recommended && concept.recommendation_reason && (
        <div className="notice notice-good"><strong>Recommended:</strong> {concept.recommendation_reason}</div>
      )}
      {concept.feasibility_note && (
        <div className="notice notice-warn"><strong>Feasibility note:</strong> {concept.feasibility_note}</div>
      )}
      <p>{concept.layout_summary}</p>

      {concept.floors.length > 1 && (
        <div className="tabs tabs-small" role="tablist">
          {concept.floors.map((f, i) => (
            <button key={f.name} role="tab" aria-selected={i === floorIndex}
                    className={i === floorIndex ? "tab tab-active" : "tab"} onClick={() => setFloorIndex(i)}>
              {f.name}
            </button>
          ))}
        </div>
      )}
      <FloorPlanSVG floor={floor} parking={floorIndex === 0 ? concept.parking : null}
                    plotWidth={request.plot_width_ft} plotLength={request.plot_length_ft} />

      <div className="detail-grid">
        <section>
          <h4>Room-wise dimensions</h4>
          <RoomTable concept={concept} />
        </section>
        <section>
          <h4>Space utilization</h4>
          <p>{concept.space_utilization}</p>
          <h4>Parking and space</h4>
          <p>{concept.parking_impact}</p>
          <h4>Advantages</h4>
          <ul>{concept.advantages.map((a) => <li key={a}>{a}</li>)}</ul>
        </section>
      </div>
      <h4>AI-generated images</h4>
      <ImageGallery designId={design.id} autoGenerate={design.is_recommended} />
      <BudgetNote note={concept.budget_note} budget={request.budget_inr} />
    </div>
  );
}

export default function DesignTabs({ designs, request }) {
  const start = designs.find((d) => d.is_recommended) || designs[0];
  const [selectedId, setSelectedId] = useState(start.id);
  const selected = designs.find((d) => d.id === selectedId) || start;

  return (
    <section className="card">
      <h2>Design concepts</h2>
      <div className="tabs" role="tablist">
        {designs.map((d) => (
          <button key={d.id} role="tab" aria-selected={d.id === selected.id}
                  className={d.id === selected.id ? "tab tab-active" : "tab"} onClick={() => setSelectedId(d.id)}>
            {d.concept_name}
            {d.is_recommended && <span className="badge">Recommended</span>}
          </button>
        ))}
      </div>
      <DesignDetail key={selected.id} design={selected} request={request} />
    </section>
  );
}
