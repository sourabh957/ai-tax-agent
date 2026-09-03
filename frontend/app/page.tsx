import Link from "next/link";
import { ArrowRight, FileText, MessageSquare, Shield, Zap } from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-full bg-white">
      {/* Nav */}
      <nav className="border-b border-slate-100 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-slate-900 flex items-center justify-center">
              <span className="text-white text-xs font-bold">T</span>
            </div>
            <span className="font-semibold text-slate-900">Taxly</span>
          </div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 transition-colors"
          >
            Get Started <ArrowRight size={14} />
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-5xl mx-auto px-6 pt-20 pb-16 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600 mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          Powered by Amazon Bedrock + deterministic tax engine
        </div>

        <h1 className="text-4xl sm:text-5xl font-semibold text-slate-900 leading-tight tracking-tight max-w-2xl mx-auto">
          AI-powered tax assistance,
          <br />
          <span className="text-slate-500">grounded in your documents.</span>
        </h1>

        <p className="mt-6 text-lg text-slate-500 max-w-xl mx-auto leading-relaxed">
          Upload your tax documents, ask questions, compare tax regimes and understand
          your tax position with an AI assistant backed by deterministic calculations.
        </p>

        <div className="mt-10 flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-medium text-white hover:bg-slate-800 transition-colors"
          >
            Get Started <ArrowRight size={14} />
          </Link>
          <a
            href="#how-it-works"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-6 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
          >
            How it works
          </a>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="max-w-5xl mx-auto px-6 py-16">
        <h2 className="text-xl font-semibold text-slate-900 text-center mb-10">
          How it works
        </h2>
        <div className="grid sm:grid-cols-3 gap-6">
          {[
            {
              icon: FileText,
              step: "1",
              title: "Upload documents",
              desc: "Upload your Form 16, AIS, broker statements and salary documents for any financial year.",
            },
            {
              icon: Zap,
              step: "2",
              title: "AI extracts and analyses",
              desc: "The agent extracts information, retrieves relevant tax rules, and runs deterministic calculations.",
            },
            {
              icon: MessageSquare,
              step: "3",
              title: "Ask and understand",
              desc: "Ask questions in plain language and get grounded answers with citations and tax breakdowns.",
            },
          ].map(({ icon: Icon, step, title, desc }) => (
            <div key={step} className="rounded-2xl border border-slate-100 bg-slate-50 p-6">
              <div className="w-8 h-8 rounded-lg bg-white border border-slate-200 flex items-center justify-center text-xs font-semibold text-slate-600 mb-4">
                {step}
              </div>
              <h3 className="font-medium text-slate-900 mb-2">{title}</h3>
              <p className="text-sm text-slate-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Security note */}
      <section className="max-w-5xl mx-auto px-6 py-12 border-t border-slate-100">
        <div className="flex flex-col sm:flex-row items-start gap-4">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center shrink-0">
            <Shield size={16} className="text-emerald-600" />
          </div>
          <div>
            <h3 className="font-medium text-slate-900 mb-1">Privacy and accuracy</h3>
            <p className="text-sm text-slate-500 leading-relaxed max-w-lg">
              Tax calculations are performed by a deterministic engine — the AI only explains results.
              Your documents are stored securely in AWS S3 with encryption. Tax rules are retrieved from
              a verified knowledge base, and every answer includes citations.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-100 px-6 py-6 text-center text-xs text-slate-400">
        © {new Date().getFullYear()} Taxly. For informational purposes only. Not financial or legal advice.
      </footer>
    </div>
  );
}
