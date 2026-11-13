import { Component } from "react";

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Uncaught render error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="error-fallback" role="alert">
          <div className="card error-box">
            <h2>Something went wrong</h2>
            <p>{this.state.error?.message || "An unexpected UI error occurred."}</p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.hash = "#/";
                window.location.reload();
              }}
            >
              Return to Upload
            </button>
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}
