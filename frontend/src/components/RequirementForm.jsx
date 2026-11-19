// RequirementForm.jsx - the requirements form with client-side validation.
// The backend validates again, this just gives instant feedback.
import { useState } from "react";

const EMPTY = {
  plot_size_sqft: "", plot_width_ft: "", plot_length_ft: "", bhk_type: "",
  bathrooms: "", floors: "", budget_inr: "", style: "", parking: "",
};
const NUMBER_FIELDS = ["plot_size_sqft", "plot_width_ft", "plot_length_ft", "bathrooms", "budget_inr"];

// Returns {fieldName: message} for every problem found.
function validate(values) {
  const errors = {};
  for (const key of Object.keys(EMPTY)) {
    if (values[key] === "") errors[key] = "Required";
  }
  for (const key of NUMBER_FIELDS) {
    if (values[key] !== "" && !(Number(values[key]) > 0)) errors[key] = "Must be a positive number";
  }
  const baths = Number(values.bathrooms);
  if (values.bathrooms !== "" && (!Number.isInteger(baths) || baths > 6)) {
    errors.bathrooms = "Enter a whole number from 1 to 6";
  }
  return errors;
}

// A mismatch is only a warning, so the user can still submit (same 10% rule as the backend).
function plotMismatchWarning(values) {
  const area = Number(values.plot_width_ft) * Number(values.plot_length_ft);
  const size = Number(values.plot_size_sqft);
  if (!(area > 0) || !(size > 0) || Math.abs(size - area) / area <= 0.1) return "";
  return `Plot size (${size} sq ft) does not match width x length (${area} sq ft). The design will use width x length.`;
}

function Field({ label, error, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}

export default function RequirementForm({ onSubmit, loading }) {
  const [values, setValues] = useState(EMPTY);
  const [submitted, setSubmitted] = useState(false);

  const errors = validate(values);
  const showErrors = submitted ? errors : {};
  const mismatch = plotMismatchWarning(values);

  function update(event) {
    setValues({ ...values, [event.target.name]: event.target.value });
  }

  function handleSubmit(event) {
    event.preventDefault();
    setSubmitted(true);
    if (Object.keys(errors).length > 0) return;
    const payload = { ...values };
    for (const key of NUMBER_FIELDS) payload[key] = Number(values[key]);
    onSubmit(payload);
  }

  const number = (name, placeholder) => (
    <input type="number" name={name} value={values[name]} onChange={update} placeholder={placeholder} min="1" step="any" />
  );
  const select = (name, options) => (
    <select name={name} value={values[name]} onChange={update}>
      <option value="">Select...</option>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );

  return (
    <form className="card form" onSubmit={handleSubmit} noValidate>
      <h2>Your requirements</h2>
      <div className="form-grid">
        <Field label="Plot size (sq ft)" error={showErrors.plot_size_sqft}>{number("plot_size_sqft", "e.g. 1000")}</Field>
        <Field label="Plot width (ft)" error={showErrors.plot_width_ft}>{number("plot_width_ft", "e.g. 25")}</Field>
        <Field label="Plot length (ft)" error={showErrors.plot_length_ft}>{number("plot_length_ft", "e.g. 40")}</Field>
        <Field label="Bedrooms" error={showErrors.bhk_type}>{select("bhk_type", ["2BHK", "3BHK"])}</Field>
        <Field label="Bathrooms" error={showErrors.bathrooms}>{number("bathrooms", "e.g. 2")}</Field>
        <Field label="Floors" error={showErrors.floors}>{select("floors", ["Ground Floor", "G+1"])}</Field>
        <Field label="Construction budget (INR)" error={showErrors.budget_inr}>{number("budget_inr", "e.g. 3000000")}</Field>
        <Field label="Design preference" error={showErrors.style}>{select("style", ["Modern", "Traditional", "Luxury"])}</Field>
        <Field label="Parking" error={showErrors.parking}>
          {select("parking", ["No parking", "Two-wheeler only", "1 car", "2 cars"])}
        </Field>
      </div>
      {mismatch && <div className="notice notice-warn">{mismatch}</div>}
      <button type="submit" className="btn" disabled={loading}>
        {loading ? "Generating..." : "Generate designs"}
      </button>
    </form>
  );
}
