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
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-8 lg:px-16 py-5">
      
      {/* Left: Logo */}
      <a href="#" className="flex items-center gap-3 shrink-0">
        <img src="/logo.jpg" alt="CodeSentinel" className="w-[32px] h-[32px] rounded-full object-cover border border-[#242428]" />
        <span className="font-semibold text-foreground text-xl tracking-tight uppercase">CodeSentinel</span>
      </a>

      {/* Center: Nav links */}
      <div className="hidden md:flex items-center gap-8">
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
      <div className="hidden md:flex items-center gap-4">
        <a 
          href="/admin"
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

    </nav>
  )
}
