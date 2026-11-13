import { useState, useEffect, useCallback } from "react";
import { getDocuments, deleteDocument, deleteAllDocuments } from "../api";

export function HistoryView() {
  const [documents, setDocuments] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDocuments(statusFilter);
      setDocuments(data || []);
    } catch (err) {
      setError(err.message || "Failed to load document history.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  const handleDeleteOne = async (e, id, filename) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete "${filename}"?`)) {
      return;
    }
    try {
      await deleteDocument(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleDeleteAll = async () => {
    const confirmed = window.confirm(
      "WARNING: This will permanently delete ALL documents and previews. Are you sure?"
    );
    if (!confirmed) return;

    try {
      await deleteAllDocuments();
      setDocuments([]);
    } catch (err) {
      alert(`Delete all failed: ${err.message}`);
    }
  };

  const formatLocalDate = (isoStr) => {
    if (!isoStr) return "—";
    try {
      const d = new Date(isoStr);
      return d.toLocaleString(undefined, {
        dateStyle: "short",
        timeStyle: "short",
      });
    } catch {
      return isoStr;
    }
  };

  return (
    <div className="history-container">
      <div className="history-header">
        <div>
          <h2>Document History</h2>
          <p className="subtitle">View, review, and manage processed invoices.</p>
        </div>
        <div className="history-actions">
          <label htmlFor="status-filter" className="sr-only">Filter by status</label>
          <select
            id="status-filter"
            className="select-input"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="extracted">Extracted</option>
            <option value="needs_review">Needs Review</option>
            <option value="reviewed">Reviewed</option>
          </select>

          <a
            href="/api/documents/export.csv?status=reviewed"
            download
            className="btn btn-secondary"
            title="Export all reviewed documents to CSV"
          >
            Export reviewed (CSV)
          </a>

          <button
            type="button"
            className="btn btn-danger"
            onClick={handleDeleteAll}
            disabled={documents.length === 0}
          >
            Delete all my data
          </button>
        </div>
      </div>

      <div aria-live="polite">
        {error && <div className="alert alert-error">{error}</div>}
      </div>

      {loading ? (
        <div className="loading-state">
          <div className="spinner" /> Loading documents...
        </div>
      ) : documents.length === 0 ? (
        <div className="card empty-state">
          <div className="empty-icon" aria-hidden="true">📂</div>
          <h3>No documents found</h3>
          <p>
            {statusFilter !== "all"
              ? `There are no documents matching the status "${statusFilter.replace("_", " ")}".`
              : "Upload your first invoice or receipt to get started."}
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => (window.location.hash = "#/")}
          >
            Upload Document
          </button>
        </div>
      ) : (
        <div className="card table-card">
          <div className="table-responsive">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Uploaded</th>
                  <th>Vendor</th>
                  <th>Total</th>
                  <th>Pages</th>
                  <th>Status</th>
                  <th aria-label="Actions"></th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr
                    key={doc.id}
                    className="clickable-row"
                    onClick={() => (window.location.hash = `#/doc/${doc.id}`)}
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") window.location.hash = `#/doc/${doc.id}`; }}
                  >
                    <td className="doc-name">
                      <strong>{doc.filename}</strong>
                    </td>
                    <td>{formatLocalDate(doc.created_at)}</td>
                    <td>{doc.vendor || <span className="muted">—</span>}</td>
                    <td>
                      {doc.total != null ? (
                        <strong>
                          {doc.currency ? `${doc.currency} ` : ""}
                          {doc.total.toFixed(2)}
                        </strong>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>{doc.page_count}</td>
                    <td>
                      <span className={`status-badge badge-${doc.status}`}>
                        {doc.status.replace("_", " ")}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn-icon-danger"
                        title="Delete document"
                        aria-label={`Delete ${doc.filename}`}
                        onClick={(e) => handleDeleteOne(e, doc.id, doc.filename)}
                      >
                        🗑️
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
