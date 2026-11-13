import { useState } from 'react'
import './App.css'

export default function App() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const handleUpload = async (e) => {
    e.preventDefault()
    if (!file) {
      setError({ message: 'Please select a document file to upload.' })
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('/api/extract', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      if (!response.ok) {
        setError(data.error || { message: 'Upload failed.' })
      } else {
        setResult(data)
      }
    } catch (err) {
      setError({ message: err.message || 'Network error occurred.' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <h1>AI Document-to-Data Extractor</h1>
      <p className="subtitle">Upload an invoice or receipt to extract structured data</p>

      <form onSubmit={handleUpload} className="upload-form">
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={(e) => setFile(e.target.files[0] || null)}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !file}>
          {loading ? 'Processing...' : 'Upload & Extract'}
        </button>
      </form>

      {error && (
        <div className="error-box">
          <strong>Error:</strong> {error.message}
        </div>
      )}

      {result && (
        <div className="result-section">
          <h2>{result.filename} ({result.mime_type})</h2>
          <p>{result.message}</p>
          <p>Pages processed: {result.page_count}</p>

          <div className="previews-grid">
            {result.pages.map((p) => (
              <div key={p.page} className="preview-card">
                <span className="page-label">Page {p.page} ({p.width}x{p.height})</span>
                <img
                  src={p.preview_url}
                  alt={`Preview of page ${p.page}`}
                  className="preview-image"
                />
              </div>
            ))}
          </div>

          {/* Extraction error */}
          {result.extraction_error && (
            <div className="error-box" style={{ marginTop: '1.5rem' }}>
              <strong>Extraction Error ({result.extraction_error.code}):</strong>{' '}
              {result.extraction_error.message}
            </div>
          )}

          {/* Extracted JSON */}
          {result.extraction && (
            <div className="extraction-section">
              <h3>Extracted Data</h3>
              <pre className="json-block">
                {JSON.stringify(result.extraction, null, 2)}
              </pre>
              {result.extraction_meta && (
                <p className="meta-info">
                  Model: {result.extraction_meta.model} |
                  Latency: {result.extraction_meta.latency_ms}ms |
                  Tokens: {result.extraction_meta.input_tokens} in / {result.extraction_meta.output_tokens} out |
                  Pages sent: {result.extraction_meta.pages_sent?.join(', ')} |
                  Repaired: {result.extraction_meta.repaired ? 'yes' : 'no'}
                </p>
              )}
            </div>
          )}

          {/* Validation flags */}
          {result.flags && Object.keys(result.flags).length > 0 && (
            <div className="flags-section">
              <h3>Validation Flags</h3>
              <ul className="flags-list">
                {Object.entries(result.flags).map(([field, flag]) => (
                  <li
                    key={field}
                    className={flag.severity === 'error' ? 'flag-error' : 'flag-warning'}
                  >
                    <strong>[{flag.severity.toUpperCase()}] {field}:</strong> {flag.message} ({flag.code})
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.needs_review !== undefined && (
            <p className="review-badge" style={{
              color: result.needs_review ? '#cf222e' : '#1a7f37',
              fontWeight: 600,
              marginTop: '1rem',
            }}>
              {result.needs_review ? '⚠ Needs Review' : '✓ Looks Good'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
