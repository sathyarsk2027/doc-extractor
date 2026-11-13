export function FlagMessage({ flag }) {
  if (!flag) return null;

  const severity = flag.severity === "error" ? "flag-error" : "flag-warning";
  const icon = flag.severity === "error" ? "⚠️" : "ℹ️";

  return (
    <div className={`flag-message ${severity}`} role="alert">
      <span className="flag-icon" aria-hidden="true">{icon}</span>
      <span className="flag-text">{flag.message}</span>
    </div>
  );
}

export function FlagSummaryBanner({ flags, error }) {
  const flagEntries = Object.entries(flags || {});
  const errorCount = flagEntries.filter(([, f]) => f.severity === "error").length;
  const warningCount = flagEntries.filter(([, f]) => f.severity === "warning").length;
  const totalCount = flagEntries.length;

  if (error) {
    return (
      <div className="summary-banner banner-error" role="alert">
        <span className="banner-icon" aria-hidden="true">⛔</span>
        <div className="banner-content">
          <strong>Extraction Issue ({error.code}): </strong>
          <span>{error.message}</span>
        </div>
      </div>
    );
  }

  if (totalCount === 0) {
    return (
      <div className="summary-banner banner-success" role="status">
        <span className="banner-icon" aria-hidden="true">✅</span>
        <div className="banner-content">
          <strong>All checks passed: </strong>
          <span>Extracted values are consistent and complete.</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`summary-banner ${errorCount > 0 ? "banner-error" : "banner-warning"}`} role="alert">
      <span className="banner-icon" aria-hidden="true">⚠️</span>
      <div className="banner-content">
        <strong>Needs review: {totalCount} {totalCount === 1 ? "issue" : "issues"} detected</strong>
        <span>
          {errorCount > 0 ? ` (${errorCount} error${errorCount > 1 ? "s" : ""}` : ""}
          {warningCount > 0 ? `${errorCount > 0 ? ", " : " ("}${warningCount} warning${warningCount > 1 ? "s" : ""}` : ""}
          {")"} — Please verify or correct the highlighted fields below.
        </span>
      </div>
    </div>
  );
}
