// ModifyPanel.jsx - version list (v1, v2, v3...) plus a form to edit the viewed version and regenerate.
// Only the edited fields are sent, so everything else keeps the old value.
import { useState } from "react";

const SELECTS = {
  bhk_type: ["2BHK", "3BHK"],
  floors: ["Ground Floor", "G+1"],
  style: ["Modern", "Traditional", "Luxury"],
  parking: ["No parking", "Two-wheeler only", "1 car", "2 cars"],
};
const LABELS = {
  bhk_type: "Bedrooms", bathrooms: "Bathrooms", floors: "Floors",
  budget_inr: "Budget (INR)", style: "Style", parking: "Parking",
};
const NUMBER_FIELDS = ["bathrooms", "budget_inr"];

// Turn the saved request into the editable draft (all values as strings).
function toDraft(request) {
  return Object.fromEntries(Object.keys(LABELS).map((key) => [key, String(request[key])]));
}

// Fields whose draft value differs from the saved value, converted back to numbers where needed.
function findChanges(request, draft) {
  const changes = {};
  for (const key of Object.keys(LABELS)) {
    if (draft[key] === String(request[key])) continue;
    changes[key] = NUMBER_FIELDS.includes(key) ? Number(draft[key]) : draft[key];
  }
  return changes;
}

function validate(changes) {
  if ("bathrooms" in changes && !(Number.isInteger(changes.bathrooms) && changes.bathrooms >= 1 && changes.bathrooms <= 6)) {
    return "Bathrooms must be a whole number from 1 to 6.";
  }
  if ("budget_inr" in changes && !(changes.budget_inr > 0)) return "Budget must be a positive number.";
  return "";
}

function VersionList({ versions, currentId, busy, onSelect }) {
  return (
    <ul className="version-list">
      {versions.map((v) => (
        <li key={v.request_id} className={v.request_id === currentId ? "version version-active" : "version"}>
          <button type="button" className="version-btn" disabled={busy} onClick={() => onSelect(v.request_id)}>
            v{v.version_number}
          </button>
          <span className="version-changes">
            {v.based_on_version && <span className="muted">from v{v.based_on_version}: </span>}
            {v.changes.join(", ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function ModifyPanel({ request, versions, loading, onSelectVersion, onModify }) {
  const [draft, setDraft] = useState(toDraft(request));
  const changes = findChanges(request, draft);
  const changedKeys = Object.keys(changes);
  const problem = validate(changes);
  const nextVersion = Math.max(0, ...versions.map((v) => v.version_number)) + 1;

  function update(event) {
    setDraft({ ...draft, [event.target.name]: event.target.value });
  }

  const input = (name) =>
    SELECTS[name] ? (
      <select name={name} value={draft[name]} onChange={update}>
        {SELECTS[name].map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    ) : (
      <input type="number" name={name} value={draft[name]} onChange={update} min="1" step="any" />
    );

  return (
    <section className="card">
      <h2>Versions and changes</h2>
      <VersionList versions={versions} currentId={request.id} busy={loading} onSelect={onSelectVersion} />

      <h3>Modify version v{request.version_number}</h3>
      <p className="muted">
        Plot: {request.plot_width_ft} x {request.plot_length_ft} ft ({request.plot_size_sqft} sq ft). Edit any
        value below. Everything you leave alone stays the same, and the result is saved as v{nextVersion}.
      </p>
      <div className="form-grid">
        {Object.keys(LABELS).map((name) => (
          <label key={name} className={`field ${name in changes ? "field-changed" : ""}`}>
            <span className="field-label">{LABELS[name]}</span>
            {input(name)}
          </label>
        ))}
      </div>
      {problem && <div className="notice notice-error">{problem}</div>}
      {changedKeys.length > 0 && !problem && (
        <p className="muted">
          Will change: {changedKeys.map((k) => `${LABELS[k]} ${request[k]} → ${changes[k]}`).join(", ")}
        </p>
      )}
      <button type="button" className="btn" disabled={loading || changedKeys.length === 0 || Boolean(problem)}
              onClick={() => onModify(changes)}>
        {loading ? "Working..." : `Regenerate as v${nextVersion}`}
      </button>
    </section>
  );
}
