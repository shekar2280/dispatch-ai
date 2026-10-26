import type { Metadata } from 'next';
import './globals.css';
import { QueryProvider } from '@/components/providers/QueryProvider';

export const metadata: Metadata = {
  title: 'Dispatch AI — AI Receptionist for Clinics',
  description: 'Dispatch AI answers every patient call on the first ring, books appointments, and sends WhatsApp confirmations — so you can focus on your patients.',
  icons: {
    icon: '/images/logo.png',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-[#F1F4EE] text-[#0D2622] selection:bg-[#F4B63A] selection:text-[#0D2622]">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
