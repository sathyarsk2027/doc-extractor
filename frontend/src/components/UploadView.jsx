import { useState, useRef } from "react";
import { extractDocument } from "../api";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg"];

export function UploadView() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const validateFile = (file) => {
    if (!file) return null;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      const ext = file.name.split(".").pop().toLowerCase();
      if (!["pdf", "png", "jpg", "jpeg"].includes(ext)) {
        return "Unsupported file type. Please upload a PDF, PNG, or JPEG file.";
      }
    }
    if (file.size > MAX_BYTES) {
      return "File exceeds the 10 MB limit. Please select a smaller file.";
    }
    return null;
  };

  const handleFileSelection = (file) => {
    if (!file) return;
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setSelectedFile(file);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    const validationError = validateFile(selectedFile);
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const doc = await extractDocument(selectedFile);
      if (doc && doc.id) {
        window.location.hash = `#/doc/${doc.id}`;
      } else {
        throw new Error("Server returned an invalid document response.");
      }
    } catch (err) {
      setError(err.message || "Extraction failed. Please check the file and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-container">
      <div className="card upload-card">
        <h2>Upload Document</h2>
        <p className="subtitle">
          Extract structured data from invoices and receipts automatically.
        </p>

        <form onSubmit={handleUpload}>
          <div
            className={`drop-zone ${isDragging ? "dragging" : ""}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                fileInputRef.current?.click();
              }
            }}
            aria-label="File upload drop zone. Click or drag a file here."
          >
            <label htmlFor="file-upload" className="sr-only">
              Choose invoice file
            </label>
            <input
              id="file-upload"
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              style={{ display: "none" }}
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  handleFileSelection(e.target.files[0]);
                }
              }}
            />

            <div className="drop-icon" aria-hidden="true">📄</div>
            <p className="drop-prompt">
              {selectedFile ? (
                <strong>Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)</strong>
              ) : (
                <>Drag &amp; drop an invoice or receipt here, or <span>browse files</span></>
              )}
            </p>
            <p className="drop-hint">Supported formats: PDF, PNG, JPG (up to 10 MB)</p>
          </div>

          <div aria-live="polite" className="error-region">
            {error && (
              <div className="alert alert-error" role="alert">
                <strong>Error: </strong> {error}
              </div>
            )}
          </div>

          {loading ? (
            <div className="loading-indicator" aria-live="polite">
              <div className="spinner" aria-hidden="true" />
              <p>Extracting... this can take up to about 30 seconds.</p>
            </div>
          ) : (
            <div className="upload-actions">
              <button
                type="submit"
                className="btn btn-primary btn-large"
                disabled={!selectedFile || loading}
              >
                Extract Data
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
