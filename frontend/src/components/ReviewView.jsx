import { useState, useEffect, useCallback } from "react";
import { getDocument, updateDocument, deleteDocument, reextractDocument } from "../api";
import { DocumentPreviewPane } from "./DocumentPreviewPane";
import { ReviewForm } from "./ReviewForm";
import { FlagSummaryBanner } from "./FlagMessage";

export function ReviewView({ documentId }) {
  const [doc, setDoc] = useState(null);
  const [formData, setFormData] = useState(null);
  const [rawNumeric, setRawNumeric] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reextracting, setReextracting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [isDirty, setIsDirty] = useState(false);
  const [hasNumericError, setHasNumericError] = useState(false);

  const initData = (docData) => {
    setDoc(docData);
    const src = docData.reviewed || docData.original || {};
    setFormData({
      vendor: src.vendor || "", invoice_number: src.invoice_number || "",
      date: src.date || "", currency: src.currency || "",
      subtotal: src.subtotal ?? null, tax: src.tax ?? null, total: src.total ?? null,
      taxable_amount: src.taxable_amount ?? null, cgst: src.cgst ?? null,
      sgst: src.sgst ?? null, igst: src.igst ?? null, cess: src.cess ?? null,
      prices_include_tax: src.prices_include_tax ?? false,
      line_items: src.line_items ? [...src.line_items] : [],
    });
    setRawNumeric({});
    setIsDirty(false);
  };

  const loadDoc = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getDocument(documentId);
      initData(data);
    } catch (err) {
      setErrorMsg(err.message || "Failed to load document.");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    loadDoc();
  }, [loadDoc]);

  // Unsaved changes warning
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  const handleFieldChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setIsDirty(true);
  };

  const handleNumericChange = (field, valStr) => {
    setRawNumeric((prev) => ({ ...prev, [field]: valStr }));
    setIsDirty(true);

    if (valStr === "") {
      setFormData((prev) => ({ ...prev, [field]: null }));
    } else {
      const parsed = parseFloat(valStr);
      if (!isNaN(parsed) && isFinite(parsed)) {
        setFormData((prev) => ({ ...prev, [field]: parsed }));
      }
    }
  };

  const hasInvalidNumericInput = () => {
    if (hasNumericError) return true;
    return Object.values(rawNumeric).some(
      (v) => v !== "" && v !== undefined && (isNaN(Number(v)) || isNaN(parseFloat(v)))
    );
  };

  const handleSave = async (markReviewed = false) => {
    if (hasInvalidNumericInput()) {
      alert("Please correct invalid numeric values before saving.");
      return;
    }
    setSaving(true);
    setErrorMsg(null);
    try {
      const updated = await updateDocument(documentId, formData, markReviewed);
      initData(updated);
    } catch (err) {
      setErrorMsg(err.message || "Failed to save changes.");
    } finally {
      setSaving(false);
    }
  };

  // Ctrl+S keybinding
  useEffect(() => {
    const onKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        handleSave(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  const handleDelete = async () => {
    if (!window.confirm("Are you sure you want to delete this document and stored files?")) {
      return;
    }
    try {
      await deleteDocument(documentId);
      window.location.hash = "#/history";
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleReextract = async () => {
    setReextracting(true);
    setErrorMsg(null);
    try {
      const updated = await reextractDocument(documentId);
      initData(updated);
    } catch (err) {
      setErrorMsg(err.message || "Re-extraction failed.");
    } finally {
      setReextracting(false);
    }
  };

  if (loading) return <div className="loading-state"><div className="spinner" /> Loading document...</div>;
  if (!doc || !formData) return <div className="alert alert-error">{errorMsg || "Document not found."}</div>;

  return (
    <div className="review-container">
      <div className="review-top-bar">
        <div className="top-left">
          <button type="button" className="btn btn-secondary btn-small" onClick={() => (window.location.hash = "#/history")}>
            &larr; Back to History
          </button>
          <h2>{doc.filename}</h2>
          <span className={`status-badge badge-${doc.status}`}>
            {doc.status.replace("_", " ")}
          </span>
          {isDirty && <span className="unsaved-badge">Unsaved changes</span>}
        </div>
        <div className="top-actions">
          {doc.error && (
            <button type="button" className="btn btn-secondary" onClick={handleReextract} disabled={reextracting}>
              {reextracting ? "Extracting..." : "Try extraction again"}
            </button>
          )}
          <button type="button" className="btn btn-secondary" onClick={() => handleSave(false)} disabled={saving}>Save changes</button>
          <button type="button" className="btn btn-primary" onClick={() => handleSave(true)} disabled={saving}>Mark as reviewed</button>
          <a href={`/api/documents/${documentId}/export.csv`} download className="btn btn-secondary" title={doc.status !== "reviewed" ? "Contains unreviewed data" : "Download CSV"}>
            Download CSV
          </a>
          {doc.status !== "reviewed" && <span className="unreviewed-note" title="Document contains unreviewed data">(Contains unreviewed data)</span>}
          <button type="button" className="btn btn-danger" onClick={handleDelete}>Delete</button>
        </div>
      </div>

      <FlagSummaryBanner flags={doc.flags || {}} error={doc.error} />
      {errorMsg && <div className="alert alert-error" role="alert">{errorMsg}</div>}

      <div className="review-workspace">
        <DocumentPreviewPane pages={doc.pages || []} />
        <ReviewForm
          formData={formData}
          originalData={doc.original || {}}
          flags={doc.flags || {}}
          onFieldChange={handleFieldChange}
          onNumericChange={handleNumericChange}
          rawNumeric={rawNumeric}
          onNumericValidityChange={setHasNumericError}
        />
      </div>
    </div>
  );
}
