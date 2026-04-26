"use client";

import { Component, ReactNode } from "react";

type Props = { name: string; children: ReactNode };
type State = { hasError: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    console.error(`[ErrorBoundary:${this.props.name}]`, error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="hud-panel rounded-lg p-4 text-sm text-pink-200">
          <p className="text-xs uppercase tracking-[0.2em] text-pink-300">
            Subsystem offline
          </p>
          <p className="mt-1 text-pink-100">
            VERONICA {this.props.name} subsystem has crashed. Reload the page or check the console — the rest of the command center remains operational.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
