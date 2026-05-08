"use client";

import { useEffect, useState } from "react";
import { GitBranch, GitPullRequest, GitCommit, BarChart2, Lock, Star, ChevronLeft, RefreshCw } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Repo = {
  name: string;
  full_name: string;
  description: string | null;
  language: string | null;
  private: boolean;
  stars: number;
  forks: number;
  open_issues: number;
  default_branch: string;
  url: string;
  updated_at: string;
};

type PR = {
  number: number;
  title: string;
  user: string;
  state: string;
  draft: boolean;
  created_at: string;
  updated_at: string;
  url: string;
};

type Commit = {
  sha: string;
  message: string;
  author: string;
  date: string;
  url: string;
};

type RepoStats = {
  name: string;
  description: string | null;
  language: string | null;
  stars: number;
  forks: number;
  open_issues: number;
  url: string;
  default_branch: string;
  updated_at: string;
};

type PRDetail = {
  number: number;
  title: string;
  user: string;
  state: string;
  body: string;
  base: string;
  head: string;
  url: string;
  additions: number | null;
  deletions: number | null;
  changed_files: number | null;
  diff: string;
};

type SubTab = "prs" | "commits" | "stats";

async function ghFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (data.ok === false) throw new Error(data.error ?? "GitHub error");
  return data as T;
}

const LANG_COLORS: Record<string, string> = {
  Python: "#3572A5",
  TypeScript: "#3178c6",
  JavaScript: "#f1e05a",
  HTML: "#e34c26",
  PHP: "#4F5D95",
  "Jupyter Notebook": "#DA5B0B",
  Go: "#00ADD8",
  Rust: "#dea584",
  CSS: "#563d7c",
};

export function GitHubPanel() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [reposLoading, setReposLoading] = useState(true);
  const [reposError, setReposError] = useState<string | null>(null);

  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [subTab, setSubTab] = useState<SubTab>("prs");

  const [prs, setPrs] = useState<PR[]>([]);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [stats, setStats] = useState<RepoStats | null>(null);
  const [selectedPR, setSelectedPR] = useState<PRDetail | null>(null);
  const [repoLoading, setRepoLoading] = useState(false);
  const [repoError, setRepoError] = useState<string | null>(null);

  const btn =
    "rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-3 py-1 text-xs text-[var(--accent-text)] hover:bg-[var(--accent)]/20 transition";

  async function loadRepos() {
    setReposLoading(true);
    setReposError(null);
    try {
      const data = await ghFetch<{ result: Repo[] }>("/github/repos");
      setRepos(data.result ?? []);
    } catch (e: unknown) {
      setReposError(e instanceof Error ? e.message : "Failed to load repos");
    } finally {
      setReposLoading(false);
    }
  }

  useEffect(() => { void loadRepos(); }, []);

  async function selectRepo(fullName: string) {
    setSelectedRepo(fullName);
    setSubTab("prs");
    setSelectedPR(null);
    setRepoLoading(true);
    setRepoError(null);
    try {
      const [prData, commitData, statsData] = await Promise.all([
        ghFetch<{ result: PR[] }>(`/github/${fullName}/pulls`),
        ghFetch<{ result: Commit[] }>(`/github/${fullName}/commits`),
        ghFetch<{ result: RepoStats }>(`/github/${fullName}/stats`),
      ]);
      setPrs(prData.result ?? []);
      setCommits(commitData.result ?? []);
      setStats(statsData.result ?? null);
    } catch (e: unknown) {
      setRepoError(e instanceof Error ? e.message : "Failed to load repo data");
    } finally {
      setRepoLoading(false);
    }
  }

  async function loadPRDetail(prNumber: number) {
    if (!selectedRepo) return;
    try {
      const data = await ghFetch<{ result: PRDetail }>(`/github/${selectedRepo}/pulls/${prNumber}`);
      setSelectedPR(data.result);
    } catch {
      setRepoError("Failed to load PR details");
    }
  }

  const SUB_TABS: Array<{ id: SubTab; label: string; icon: React.ReactNode }> = [
    { id: "prs", label: "PRs", icon: <GitPullRequest size={13} /> },
    { id: "commits", label: "Commits", icon: <GitCommit size={13} /> },
    { id: "stats", label: "Stats", icon: <BarChart2 size={13} /> },
  ];

  return (
    <div className="hud-panel rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-text)" }}>
          <GitBranch size={16} /> GitHub
          {selectedRepo && (
            <span className="text-slate-400 font-normal text-xs ml-1">/ {selectedRepo}</span>
          )}
        </p>
        <div className="flex items-center gap-2">
          {selectedRepo && (
            <button
              onClick={() => { setSelectedRepo(null); setSelectedPR(null); setRepoError(null); }}
              className={btn}
            >
              <ChevronLeft size={12} className="inline mr-1" />Repos
            </button>
          )}
          {!selectedRepo && (
            <button onClick={loadRepos} disabled={reposLoading} className={`${btn} flex items-center gap-1`}>
              <RefreshCw size={11} className={reposLoading ? "animate-spin" : ""} />
            </button>
          )}
        </div>
      </div>

      {/* ── Repo list ──────────────────────────────────────────────── */}
      {!selectedRepo && (
        <>
          {reposLoading && (
            <p className="text-xs text-slate-400 animate-pulse">Loading repositories…</p>
          )}
          {reposError && (
            <div className="rounded-lg border border-pink-300/40 bg-pink-400/10 px-3 py-2 text-sm text-pink-200">
              {reposError}
            </div>
          )}
          {!reposLoading && !reposError && (
            <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
              {repos.map((r) => (
                <button
                  key={r.full_name}
                  onClick={() => void selectRepo(r.full_name)}
                  className="w-full text-left rounded-lg border border-white/10 bg-black/20 p-3 hover:border-[var(--accent)]/40 hover:bg-[var(--accent)]/5 transition space-y-1"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-100 flex items-center gap-1.5">
                      {r.private && <Lock size={11} className="text-slate-500 flex-shrink-0" />}
                      {r.name}
                    </span>
                    {r.stars > 0 && (
                      <span className="flex items-center gap-0.5 text-xs text-slate-400 flex-shrink-0">
                        <Star size={11} className="text-yellow-400" />{r.stars}
                      </span>
                    )}
                  </div>
                  {r.description && (
                    <p className="text-xs text-slate-400 line-clamp-1">{r.description}</p>
                  )}
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    {r.language && (
                      <span className="flex items-center gap-1">
                        <span
                          className="w-2 h-2 rounded-full inline-block"
                          style={{ backgroundColor: LANG_COLORS[r.language] ?? "#8b949e" }}
                        />
                        {r.language}
                      </span>
                    )}
                    {r.open_issues > 0 && <span>{r.open_issues} issues</span>}
                    <span>{new Date(r.updated_at).toLocaleDateString()}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Repo detail ────────────────────────────────────────────── */}
      {selectedRepo && (
        <>
          {repoLoading && (
            <p className="text-xs text-slate-400 animate-pulse">Loading…</p>
          )}
          {repoError && (
            <div className="rounded-lg border border-pink-300/40 bg-pink-400/10 px-3 py-2 text-sm text-pink-200">
              {repoError}
            </div>
          )}

          {!repoLoading && (
            <>
              <div className="flex gap-1 rounded-lg border border-white/10 bg-black/30 p-1">
                {SUB_TABS.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => { setSubTab(t.id); setSelectedPR(null); }}
                    className={`flex items-center gap-1.5 flex-1 justify-center rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                      subTab === t.id
                        ? "bg-[var(--accent)]/20 text-[var(--accent-text)] border border-[var(--accent)]/30"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {t.icon} {t.label}
                  </button>
                ))}
              </div>

              {selectedPR ? (
                <div className="space-y-3">
                  <button onClick={() => setSelectedPR(null)} className={btn}>← Back to PRs</button>
                  <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-2">
                    <p className="text-sm font-semibold text-slate-100">
                      #{selectedPR.number} {selectedPR.title}
                    </p>
                    <p className="text-xs text-slate-400">
                      {selectedPR.user} · {selectedPR.head} → {selectedPR.base} ·{" "}
                      <a href={selectedPR.url} target="_blank" rel="noopener noreferrer" className="underline">
                        View on GitHub
                      </a>
                    </p>
                    {(selectedPR.additions != null || selectedPR.changed_files != null) && (
                      <p className="text-xs text-slate-400">
                        +{selectedPR.additions ?? 0} / -{selectedPR.deletions ?? 0} in {selectedPR.changed_files ?? 0} files
                      </p>
                    )}
                    {selectedPR.body && (
                      <p className="text-sm text-slate-300 whitespace-pre-wrap">{selectedPR.body}</p>
                    )}
                    {selectedPR.diff && (
                      <pre className="mt-2 max-h-64 overflow-auto rounded bg-black/40 p-3 text-xs text-slate-300 whitespace-pre-wrap">
                        {selectedPR.diff}
                      </pre>
                    )}
                  </div>
                </div>
              ) : (
                <>
                  {subTab === "prs" && (
                    <div className="space-y-2">
                      {prs.length === 0 ? (
                        <p className="text-sm text-slate-400">No open pull requests.</p>
                      ) : (
                        prs.map((pr) => (
                          <div
                            key={pr.number}
                            className="flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-black/20 p-3 cursor-pointer hover:border-[var(--accent)]/30 transition"
                            onClick={() => void loadPRDetail(pr.number)}
                          >
                            <div>
                              <p className="text-sm text-slate-100">
                                #{pr.number} {pr.title}
                                {pr.draft && <span className="ml-2 text-xs text-slate-500">[draft]</span>}
                              </p>
                              <p className="text-xs text-slate-400 mt-0.5">{pr.user}</p>
                            </div>
                            <span className={`text-xs px-2 py-0.5 rounded-full border flex-shrink-0 ${
                              pr.state === "open"
                                ? "border-emerald-400/40 text-emerald-300"
                                : "border-slate-500/40 text-slate-400"
                            }`}>
                              {pr.state}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {subTab === "commits" && (
                    <div className="space-y-2">
                      {commits.length === 0 ? (
                        <p className="text-sm text-slate-400">No commits found.</p>
                      ) : (
                        commits.map((c) => (
                          <a
                            key={c.sha}
                            href={c.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block rounded-lg border border-white/10 bg-black/20 p-3 hover:border-[var(--accent)]/30 transition"
                          >
                            <p className="text-sm text-slate-100 font-mono">
                              <span className="text-[var(--accent-text)] mr-2">{c.sha}</span>
                              {c.message}
                            </p>
                            <p className="text-xs text-slate-400 mt-0.5">
                              {c.author} · {new Date(c.date).toLocaleDateString()}
                            </p>
                          </a>
                        ))
                      )}
                    </div>
                  )}

                  {subTab === "stats" && stats && (
                    <div className="rounded-lg border border-white/10 bg-black/20 p-4 space-y-3">
                      <a href={stats.url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-[var(--accent-text)] underline">
                        {stats.name}
                      </a>
                      {stats.description && <p className="text-sm text-slate-300">{stats.description}</p>}
                      <div className="grid grid-cols-3 gap-3 mt-2">
                        {[
                          { label: "Stars", value: stats.stars },
                          { label: "Forks", value: stats.forks },
                          { label: "Issues", value: stats.open_issues },
                        ].map((s) => (
                          <div key={s.label} className="rounded-lg border border-white/10 bg-black/30 p-2 text-center">
                            <p className="text-lg font-bold text-slate-100">{s.value}</p>
                            <p className="text-xs text-slate-400">{s.label}</p>
                          </div>
                        ))}
                      </div>
                      <p className="text-xs text-slate-400">
                        {stats.language && <span className="mr-3">Language: {stats.language}</span>}
                        Default branch: {stats.default_branch}
                      </p>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
