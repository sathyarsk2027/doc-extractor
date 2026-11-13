import { useState, useEffect } from "react";
import { UploadView } from "./components/UploadView";
import { HistoryView } from "./components/HistoryView";
import { ReviewView } from "./components/ReviewView";
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./App.css";

export default function App() {
  const [currentHash, setCurrentHash] = useState(window.location.hash || "#/");

  useEffect(() => {
    const onHashChange = () => {
      setCurrentHash(window.location.hash || "#/");
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const renderRoute = () => {
    const hash = currentHash.trim();
    if (hash.startsWith("#/doc/")) {
      const docId = hash.replace("#/doc/", "").split("?")[0].split("/")[0];
      return <ReviewView documentId={docId} />;
    }
    if (hash === "#/history") {
      return <HistoryView />;
    }
    return <UploadView />;
  };

  const isUploadActive = currentHash === "#/" || currentHash === "";
  const isHistoryActive = currentHash === "#/history";

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-container">
          <div className="logo-group" onClick={() => (window.location.hash = "#/")} role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") window.location.hash = "#/"; }}>
            <span className="logo-icon" aria-hidden="true">📑</span>
            <span className="logo-text">AI Document Extractor</span>
          </div>

          <nav className="app-nav" aria-label="Main Navigation">
            <a
              href="#/"
              className={`nav-link ${isUploadActive ? "active" : ""}`}
              aria-current={isUploadActive ? "page" : undefined}
            >
              Upload
            </a>
            <a
              href="#/history"
              className={`nav-link ${isHistoryActive ? "active" : ""}`}
              aria-current={isHistoryActive ? "page" : undefined}
            >
              History
            </a>
          </nav>
        </div>
      </header>

      <main className="app-main">
        <ErrorBoundary>
          {renderRoute()}
        </ErrorBoundary>
      </main>
    </div>
  );
}
