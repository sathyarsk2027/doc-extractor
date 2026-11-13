import { useState } from "react";

export function DocumentPreviewPane({ pages = [] }) {
  const [currentPage, setCurrentPage] = useState(1);
  const [zoomMode, setZoomMode] = useState("fit"); // "fit" or "actual"

  if (!pages || pages.length === 0) {
    return (
      <div className="preview-pane empty-preview">
        <p>No preview images available for this document.</p>
      </div>
    );
  }

  const activePage = pages.find((p) => p.page === currentPage) || pages[0];

  return (
    <div className="preview-pane">
      <div className="preview-toolbar">
        {pages.length > 1 && (
          <div className="page-tabs" role="tablist" aria-label="Document pages">
            {pages.map((p) => (
              <button
                key={p.page}
                type="button"
                role="tab"
                aria-selected={p.page === currentPage}
                className={`tab-btn ${p.page === currentPage ? "active" : ""}`}
                onClick={() => setCurrentPage(p.page)}
              >
                Page {p.page}
              </button>
            ))}
          </div>
        )}

        <div className="zoom-toggle">
          <button
            type="button"
            className={`btn btn-secondary btn-small ${zoomMode === "fit" ? "active" : ""}`}
            onClick={() => setZoomMode(zoomMode === "fit" ? "actual" : "fit")}
            title="Toggle between fit-to-width and original 100% size"
          >
            {zoomMode === "fit" ? "Zoom 100%" : "Fit Width"}
          </button>
        </div>
      </div>

      <div className={`preview-viewport ${zoomMode === "fit" ? "mode-fit" : "mode-actual"}`}>
        <img
          src={activePage.preview_url}
          alt={`Document Preview Page ${activePage.page}`}
          className="preview-image"
          loading="lazy"
        />
      </div>
    </div>
  );
}
