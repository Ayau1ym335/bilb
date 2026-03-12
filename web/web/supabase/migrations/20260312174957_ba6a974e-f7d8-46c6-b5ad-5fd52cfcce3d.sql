
CREATE TABLE public.early_access_leads (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  company TEXT,
  role TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Allow anonymous inserts (public form)
CREATE POLICY "Anyone can submit early access" ON public.early_access_leads
  FOR INSERT TO anon, authenticated
  WITH CHECK (true);

-- Only authenticated users (admins) can read
CREATE POLICY "Authenticated users can read leads" ON public.early_access_leads
  FOR SELECT TO authenticated
  USING (true);
