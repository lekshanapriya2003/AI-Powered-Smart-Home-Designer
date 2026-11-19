// App.jsx - top-level page: the form, the results and the version/modify panel.
// Holds the loading and error state for every backend call.
import { useState } from "react";
import { generateDesigns, getDesigns, getVersions, modifyDesigns } from "./api/client.js";
import RequirementForm from "./components/RequirementForm.jsx";
import DesignTabs from "./components/DesignTabs.jsx";
import ModifyPanel from "./components/ModifyPanel.jsx";

export default function App() {
  const [result, setResult] = useState(null);     // the version currently shown
  const [versions, setVersions] = useState([]);   // all versions of the current project
  const [loadingText, setLoadingText] = useState("");
  const [error, setError] = useState("");

  const loading = loadingText !== "";

  // Runs one backend action with a loading message and shared error handling.
  async function run(message, action) {
    setLoadingText(message);
    setError("");
    try {
      const data = await action();
      setResult(data);
      const list = await getVersions(data.request.project_id);
      setVersions(list.versions);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingText("");
    }
  }

  const slowMessage = "Designing 3 concepts. This can take a minute or two because each concept is checked and corrected before it is shown.";
  const handleSubmit = (values) => run(slowMessage, () => generateDesigns(values));
  const handleModify = (changes) => run(slowMessage, () => modifyDesigns(result.request.id, changes));
  const handleSelectVersion = (requestId) => run("Loading version...", () => getDesigns(requestId));

  return (
    <div className="page">
      <header className="page-header">
        <h1>AI-Powered Smart Home Designer</h1>
        <p>Enter your plot and house requirements to get 3 design concepts with 2D floor plans.</p>
      </header>

      <RequirementForm onSubmit={handleSubmit} loading={loading} />

      {loading && <div className="notice notice-info" role="status">{loadingText}</div>}
      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {result?.warnings.map((w) => <div key={w} className="notice notice-warn">{w}</div>)}

      {result && (
        <>
          <p className="version-badge">Showing version v{result.request.version_number}</p>
          {/* key = request id, so tabs and the edit form reset when another version is shown */}
          <DesignTabs key={`tabs-${result.request.id}`} designs={result.designs} request={result.request} />
          <ModifyPanel key={`mod-${result.request.id}-${versions.length}`} request={result.request}
                       versions={versions} loading={loading}
                       onSelectVersion={handleSelectVersion} onModify={handleModify} />
        </>
      )}
    </div>
  );
}
