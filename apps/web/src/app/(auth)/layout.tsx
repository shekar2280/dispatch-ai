import Link from 'next/link';
import Image from 'next/image';
import { APP_CONFIG } from '@/lib/constants';

export default function AuthLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="grid min-h-dvh grid-cols-1 bg-[#F1F4EE] lg:grid-cols-12 font-sans antialiased text-[#0D2622]">
      <aside className="sticky top-0 hidden h-dvh p-3 lg:col-span-5 lg:block xl:p-4">
        <div className="relative flex h-full flex-col justify-between overflow-hidden rounded-3xl bg-[#0D2622] border border-[rgba(13,38,34,0.16)] shadow-2xl shadow-[rgba(13,38,34,0.18)]">
          <Image
            src="/images/auth-care-illustration.png"
            alt="A doctor listening to a patient in a calm clinic"
            fill
            priority
            sizes="42vw"
            className="object-cover object-bottom"
          />
          <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-[#0D2622]/60 via-[#0D2622]/20 to-transparent" />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[48%] bg-gradient-to-t from-[#0D2622] via-[#0D2622]/70 to-transparent" />

          <div className="relative z-10 p-7 xl:p-9">
            <Link
              href="/"
              className="inline-flex w-fit items-center gap-2.5 rounded-full border border-white/20 bg-black/40 px-3.5 py-1.5 backdrop-blur-md transition hover:bg-black/60"
            >
              <Image src={APP_CONFIG.logoPath} alt="" width={22} height={22} className="h-5.5 w-5.5 rounded-md object-contain" />
              <span className="text-sm font-semibold tracking-tight text-[#F1F4EE]">
                {APP_CONFIG.name}
                <span className="font-normal text-[#BFDDCD]">{APP_CONFIG.nameAccent}</span>
              </span>
            </Link>
          </div>

          <div className="relative z-10 mt-auto p-7 xl:p-9">
            <h2 className="font-serif italic text-3xl sm:text-4xl xl:text-[44px] font-normal leading-[1.12] tracking-[-0.02em] text-[#F1F4EE] drop-shadow-md">
              For the people<br />in your care.
            </h2>
            <p className="mt-2.5 text-xs font-medium tracking-wider uppercase text-[#F4B63A]">
              Autonomous Voice Telephony & OPD Queue Engine
            </p>
          </div>
        </div>
      </aside>

      <div className="flex flex-col items-center justify-center px-4 py-8 sm:px-8 lg:col-span-7 xl:col-span-7">
        <div className="w-full max-w-[460px]">
          <div className="mb-6 flex items-center justify-between lg:hidden">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-[rgba(13,38,34,0.16)] bg-[#0D2622] shadow-sm">
                <Image src={APP_CONFIG.logoPath} alt={APP_CONFIG.name} width={20} height={20} className="h-5 w-5 object-contain" />
              </span>
              <span className="text-base font-bold tracking-tight text-[#0D2622]">
                {APP_CONFIG.name}
                <span className="text-[#1E6B56] font-medium">{APP_CONFIG.nameAccent}</span>
              </span>
            </Link>
          </div>

          <div className="rounded-3xl border border-[rgba(13,38,34,0.14)] bg-white p-7 sm:p-9 shadow-[0_20px_50px_-20px_rgba(13,38,34,0.08),0_1px_3px_rgba(0,0,0,0.03)]">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}