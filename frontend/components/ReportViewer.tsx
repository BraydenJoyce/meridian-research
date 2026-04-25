import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";

interface ReportViewerProps {
  markdown: string;
}

const components: Components = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 underline hover:text-blue-800"
    >
      {children}
    </a>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-bold text-zinc-900 mt-6 mb-2">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-lg font-semibold text-zinc-800 mt-4 mb-1">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="text-zinc-700 leading-relaxed mb-3">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc list-inside text-zinc-700 mb-3 space-y-1">{children}</ul>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  code: ({ children }) => (
    <code className="bg-zinc-100 rounded px-1 py-0.5 text-sm font-mono text-zinc-800">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="bg-zinc-900 text-zinc-100 rounded-lg p-4 overflow-x-auto text-sm my-4">
      {children}
    </pre>
  ),
};

export default function ReportViewer({ markdown }: ReportViewerProps) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-6">
      <h2 className="text-lg font-bold text-zinc-900 mb-4 border-b border-zinc-100 pb-3">
        Intelligence Report
      </h2>
      <article className="prose prose-zinc max-w-none">
        <ReactMarkdown components={components}>{markdown}</ReactMarkdown>
      </article>
    </div>
  );
}
