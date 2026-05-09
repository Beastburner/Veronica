"use client";

import { AlertTriangle } from "lucide-react";
import { Component, ReactNode } from "react";

type Props = { name: string; children: ReactNode };
type State = { hasError: boolean; error: string };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error: error.message };
  }

  componentDidCatch(error: Error) {
    console.error(`[VERONICA] ${this.props.name} subsystem error:`, error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="hud-panel rounded-lg p-4 border border-red-500/40">
          <div className="flex items-center gap-2 text-red-400 text-sm">
            <AlertTriangle size={14} />
            <span className="uppercase tracking-[0.18em] text-xs">
              VERONICA - {this.props.name.toUpperCase()} SUBSYSTEM OFFLINE
            </span>
          </div>
          {this.state.error ? (
            <p className="mt-1 text-xs text-red-300/60 font-mono break-all">
              {this.state.error}
            </p>
          ) : null}
          <button
            className="mt-2 text-xs text-red-400 hover:text-red-300 underline"
            onClick={() => this.setState({ hasError: false, error: "" })}
          >
            Attempt restart
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
