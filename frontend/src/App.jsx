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
      <p className="subtitle">Phase 2 Preprocessing Smoke Test</p>

      <form onSubmit={handleUpload} className="upload-form">
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={(e) => setFile(e.target.files[0] || null)}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !file}>
          {loading ? 'Processing...' : 'Upload'}
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
        </div>
      )}
    </div>
  )
}
