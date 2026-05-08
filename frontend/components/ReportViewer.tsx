import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { ExternalLink } from "lucide-react";

interface ReportViewerProps {
  markdown: string;
}

const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-2xl font-bold text-slate-900 mt-0 mb-4 pb-3 border-b border-slate-100">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-bold text-slate-900 mt-8 mb-3 pb-2 border-b border-slate-100 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-semibold text-slate-800 mt-5 mb-2">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-semibold text-slate-700 mt-4 mb-1.5">{children}</h4>
  ),
  p: ({ children }) => (
    <p className="text-[15px] text-slate-700 leading-relaxed mb-4">{children}</p>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-indigo-600 underline decoration-indigo-300 underline-offset-2 hover:text-indigo-700 hover:decoration-indigo-500 transition-colors inline-items-center"
    >
      {children}
      <ExternalLink className="inline w-3 h-3 ml-0.5 opacity-60" />
    </a>
  ),
  ul: ({ children }) => (
    <ul className="mb-4 space-y-1.5 list-none pl-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-4 space-y-1.5 list-decimal pl-5">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="flex items-start gap-2.5 text-[15px] text-slate-700 leading-relaxed">
      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 flex-shrink-0 mt-2.5" />
      <span>{children}</span>
    </li>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-indigo-300 pl-4 bg-indigo-50/40 py-2 pr-3 rounded-r-lg my-4 text-slate-600 italic text-[15px]">
      {children}
    </blockquote>
  ),
  code: ({ children, className }) => {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return (
        <code className={`${className} text-sm font-mono text-emerald-300`}>{children}</code>
      );
    }
    return (
      <code className="bg-slate-100 rounded px-1.5 py-0.5 text-sm font-mono text-slate-800 border border-slate-200">
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="bg-slate-900 text-slate-100 rounded-xl p-5 overflow-x-auto text-sm my-5 shadow-inner border border-slate-800">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-5 rounded-xl border border-slate-200 shadow-sm">
      <table className="w-full border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,
  th: ({ children }) => (
    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-600 border-b border-slate-200">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-4 py-3 text-sm text-slate-700 border-b border-slate-100 last-row:border-0">
      {children}
    </td>
  ),
  hr: () => <hr className="border-slate-200 my-6" />,
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900">{children}</strong>
  ),
  em: ({ children }) => <em className="italic text-slate-600">{children}</em>,
};

export default function ReportViewer({ markdown }: ReportViewerProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Report header */}
      <div className="px-8 py-5 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-5 rounded-full bg-gradient-to-b from-indigo-500 to-violet-600" />
          <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
            Intelligence Report
          </span>
        </div>
      </div>
      {/* Report body */}
      <article className="px-8 py-7">
        <ReactMarkdown components={components} remarkPlugins={[remarkGfm]}>
          {markdown}
        </ReactMarkdown>
      </article>
    </div>
  );
}
