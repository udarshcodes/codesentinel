import { adminUrl } from '../../services/adminUrl'
export default function Navbar() {
  const navLinks = [
    { label: 'Product', href: '#' },
    { label: 'How It Works', href: '#workflow' },
    { label: 'Features', href: '#features' },
    { label: 'Languages', href: '#languages' },
    { label: 'Architecture', href: '#architecture' },
    { label: 'GitHub', href: 'https://github.com/udarshcodes/codesentinel', external: true }
  ]

  return (
    <nav aria-label="Main navigation" className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between gap-4 px-8 lg:px-16 py-5">
      
      {/* Left: Logo */}
      <a href="#" className="flex items-center gap-3 shrink-0">
        <img src="/logo.jpg" alt="CodeSentinel" className="w-[32px] h-[32px] rounded-full object-cover border border-[#242428]" />
        <span className="font-semibold text-foreground text-xl tracking-tight uppercase">CodeSentinel</span>
      </a>

      {/* Center: Nav links */}
      <div className="hidden 2xl:flex items-center gap-8">
        {navLinks.map((link) => (
          <a 
            key={link.label}
            href={link.href}
            target={link.external ? "_blank" : undefined}
            rel={link.external ? "noreferrer" : undefined}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors uppercase tracking-widest"
          >
            {link.label}
          </a>
        ))}
      </div>

      {/* Right: CTA */}
      <div className="hidden 2xl:flex items-center gap-4">
        <a 
          href={adminUrl()}
          target="_blank" 
          rel="noopener noreferrer"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors uppercase tracking-widest"
        >
          Admin
        </a>
        <button 
          onClick={() => document.getElementById('repo-analyzer')?.scrollIntoView({ behavior: 'smooth' })}
          className="text-foreground bg-nav-button hover:bg-nav-button/80 active:scale-[0.97] transition-all rounded-lg uppercase text-xs tracking-widest px-6 py-3 font-semibold"
        >
          Analyze Repository
        </button>
      </div>

      <details className="relative 2xl:hidden text-[#FAFAFA]">
        <summary className="cursor-pointer px-3 py-2 rounded-lg border border-[#52525B]">Menu</summary>
        <div className="absolute right-0 top-full mt-3 w-56 max-h-[70dvh] overflow-y-auto rounded-xl border border-[#242428] bg-[#0A0A0A] p-3 shadow-xl">
          {navLinks.map(link => (
            <a key={link.label} href={link.href} target={link.external ? '_blank' : undefined} rel={link.external ? 'noreferrer' : undefined}
              onClick={event => event.currentTarget.closest('details')?.removeAttribute('open')}
              className="block px-3 py-3 text-sm hover:bg-white/10 rounded-md">{link.label}</a>
          ))}
          <a href={adminUrl()} className="block px-3 py-3 text-sm hover:bg-white/10 rounded-md">Admin Dashboard</a>
          <a href="#repo-analyzer" onClick={event => event.currentTarget.closest('details')?.removeAttribute('open')}
            className="block px-3 py-3 text-sm text-primary rounded-md">Analyze Repository</a>
        </div>
      </details>

    </nav>
  )
}
