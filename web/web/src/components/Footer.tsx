const Footer = () => {
  return (
    <footer className="border-t border-border/30 py-12">
      <div className="mx-auto max-w-6xl px-6">
        <div className="flex flex-col items-center justify-between gap-8 md:flex-row">
          <div>
            <h3 className="font-serif text-2xl font-bold text-primary">BILB</h3>
            <p className="mt-1 font-sans text-xs tracking-widest text-muted-foreground">
              Brighter with history
            </p>
          </div>

          <nav className="flex gap-8 font-sans text-sm text-muted-foreground">
            <a href="#" className="hover:text-foreground transition-colors">Product</a>
            <a href="#" className="hover:text-foreground transition-colors">Vision</a>
            <a href="#" className="hover:text-foreground transition-colors">Pricing</a>
            <a href="#early-access" className="hover:text-foreground transition-colors">Early Access</a>
          </nav>

          <div className="text-right">
            <p className="font-sans text-xs text-muted-foreground">Contact</p>
            <a href="mailto:bilb.robotic@gmail.com" className="font-sans text-sm text-primary hover:underline">
              bilb.robotic@gmail.com
            </a>
          </div>
        </div>

        <div className="mt-8 text-center">
          <p className="font-sans text-xs text-muted-foreground">
            © {new Date().getFullYear()} BILB. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
