// ImageGallery.jsx - shows the 4 AI images of one design.
// The recommended design generates its images automatically; others wait for a button click to save free quota.
import { useEffect, useRef, useState } from "react";
import { generateImages, getImages, imageUrl } from "../api/client.js";

const TOTAL_IMAGES = 4;
const LABELS = { exterior: "3D exterior", living_room: "Living room", bedroom: "Bedroom", kitchen: "Kitchen" };

export default function ImageGallery({ designId, autoGenerate }) {
  const [images, setImages] = useState([]);
  const [failed, setFailed] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | idle | generating | error
  const [error, setError] = useState("");
  const startedRef = useRef(false); // stops React's dev double-mount from starting two generations

  async function generate() {
    setStatus("generating");
    setError("");
    try {
      const result = await generateImages(designId);
      setImages(result.images);
      setFailed(result.failed);
      setStatus("idle");
    } catch (err) {
      setError(err.message);
      setStatus("error");
    }
  }

  // On open: show anything already saved. Only the recommended design then fills in the missing images.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    (async () => {
      try {
        const saved = await getImages(designId);
        setImages(saved.images);
        if (autoGenerate && saved.images.length < TOTAL_IMAGES) await generate();
        else setStatus("idle");
      } catch (err) {
        setError(err.message);
        setStatus("error");
      }
    })();
  }, []);

  const busy = status === "loading" || status === "generating";
  const buttonLabel = images.length === 0 ? "Generate images" : "Generate missing images";

  return (
    <div className="gallery">
      {status === "generating" && (
        <div className="notice notice-info" role="status">
          Generating images. This usually takes under a minute, longer if the backup service is used.
        </div>
      )}
      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {failed.length > 0 && (
        <div className="notice notice-warn">
          Could not generate: {failed.map((t) => LABELS[t] || t).join(", ")}. You can try again.
        </div>
      )}

      {images.length > 0 && (
        <div className="gallery-grid">
          {images.map((img) => (
            <figure key={img.image_type}>
              <img src={imageUrl(img.url)} alt={LABELS[img.image_type]} loading="lazy" />
              <figcaption>{LABELS[img.image_type]} <span className="muted">({img.provider})</span></figcaption>
            </figure>
          ))}
        </div>
      )}

      {images.length < TOTAL_IMAGES && !busy && (
        <button type="button" className="btn btn-secondary" onClick={generate}>{buttonLabel}</button>
      )}
      {images.length > 0 && (
        <p className="muted">AI-generated illustrations. They show the style and colours, not the exact floor plan.</p>
      )}
    </div>
  );
}
