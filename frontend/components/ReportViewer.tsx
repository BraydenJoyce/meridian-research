import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { ExternalLink } from "lucide-react";

interface ReportViewerProps {
  markdown: string;
}

const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-3xl font-bold tracking-tight text-slate-900 mt-0 mb-6 leading-tight">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-bold text-slate-900 mt-10 mb-4 first:mt-0 leading-snug">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-semibold text-slate-800 mt-7 mb-2 leading-snug">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-semibold text-slate-700 mt-5 mb-1.5">{children}</h4>
  ),
  p: ({ children }) => (
    <p className="text-[16px] text-slate-600 leading-[1.8] mb-5">{children}</p>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-indigo-600 underline decoration-indigo-200 underline-offset-2 hover:text-indigo-700 hover:decoration-indigo-400 transition-colors"
    >
      {children}
      <ExternalLink className="inline w-3 h-3 ml-0.5 opacity-50" />
    </a>
  ),
  ul: ({ children }) => (
    <ul className="mb-5 space-y-2 list-none pl-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-5 space-y-2 list-decimal pl-5">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="flex items-start gap-3 text-[16px] text-slate-600 leading-[1.8]">
      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 flex-shrink-0 mt-[11px]" />
      <span>{children}</span>
    </li>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-indigo-300 pl-5 bg-indigo-50/40 py-3 pr-4 rounded-r-xl my-5 text-slate-600 italic text-[16px] leading-[1.8]">
      {children}
    </blockquote>
  ),
  code: ({ children, className }) => {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return <code className={`${className} text-sm font-mono text-emerald-300`}>{children}</code>;
    }
    return (
      <code className="bg-slate-100 rounded-md px-1.5 py-0.5 text-[14px] font-mono text-slate-800 border border-slate-200">
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="bg-[#0d0d1c] text-slate-200 rounded-2xl p-5 overflow-x-auto text-sm my-6 border border-white/[0.06]">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-6 rounded-2xl border border-slate-100 shadow-[0_1px_3px_rgba(0,0,0,0.05)]">
      <table className="w-full border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-50">{children}</thead>,
  th: ({ children }) => (
    <th className="px-5 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide border-b border-slate-100">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-5 py-3 text-[15px] text-slate-600 border-b border-slate-50 last:border-0">
      {children}
    </td>
  ),
  hr: () => <hr className="border-slate-100 my-8" />,
  strong: ({ children }) => (
    <strong className="font-semibold text-slate-900">{children}</strong>
  ),
  em: ({ children }) => <em className="italic text-slate-500">{children}</em>,
};

export default function ReportViewer({ markdown }: ReportViewerProps) {
  return (
    <div className="bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.05)] overflow-hidden">
      {/* Report header */}
      <div className="px-8 py-4 border-b border-slate-100 flex items-center gap-2">
        <span className="w-1.5 h-4 rounded-full bg-gradient-to-b from-indigo-500 to-violet-600" />
        <span className="text-xs font-semibold text-indigo-600 uppercase tracking-widest">
          Intelligence Report
        </span>
      </div>
      {/* Body */}
      <article className="px-8 py-8 max-w-[72ch]">
        <ReactMarkdown components={components} remarkPlugins={[remarkGfm]}>
          {markdown}
        </ReactMarkdown>
      </article>
    </div>
  );
}
