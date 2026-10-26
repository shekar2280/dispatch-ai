import { countries, getCountryData, getEmojiFlag, TCountryCode } from 'countries-list';
import { currencies } from 'countries-list/currencies';
import { getTimezonesForCountry, getAllTimezones } from 'countries-and-timezones';

export interface CountryOption {
  code: string;
  name: string;
  native: string;
  flag: string;
  phoneCode: string;
  currencyCode: string;
  currencySymbol: string;
  currencyName: string;
}

export interface CurrencyOption {
  code: string;
  name: string;
  symbol: string;
}

export function getCountryProfile(isoCode: string): CountryOption {
  const upper = isoCode.trim().toUpperCase();
  const c = getCountryData(upper as TCountryCode);

  if (!c) {
    return {
      code: upper,
      name: upper,
      native: upper,
      flag: '🌐',
      phoneCode: '',
      currencyCode: '',
      currencySymbol: '',
      currencyName: '',
    };
  }

  const primaryCurrency = c.currency?.[0] || '';
  const cur = currencies[primaryCurrency as keyof typeof currencies] as any;

  return {
    code: upper,
    name: c.name,
    native: c.native || c.name,
    flag: getEmojiFlag(upper as TCountryCode) || '🌐',
    phoneCode: c.phone?.[0] ? `+${c.phone[0]}` : '',
    currencyCode: primaryCurrency,
    currencySymbol: cur?.symbol || primaryCurrency,
    currencyName: cur?.name || primaryCurrency,
  };
}

export function getAllCountries(): CountryOption[] {
  const countryKeys = Object.keys(countries);
  return countryKeys
    .sort((a, b) => countries[a as TCountryCode].name.localeCompare(countries[b as TCountryCode].name))
    .map((code) => getCountryProfile(code));
}

export const ALL_COUNTRIES: CountryOption[] = getAllCountries();

export function getAllCurrencies(): CurrencyOption[] {
  const currencyKeys = Object.keys(currencies);
  return currencyKeys.sort().map((code) => {
    const item = currencies[code as keyof typeof currencies] as any;
    return {
      code,
      name: item?.name || code,
      symbol: item?.symbol || code,
    };
  });
}

export const ALL_CURRENCIES: CurrencyOption[] = getAllCurrencies();

export function getCurrencyForCode(currencyCode: string): CurrencyOption {
  const code = currencyCode.trim().toUpperCase();
  const found = currencies[code as keyof typeof currencies] as any;
  if (found) {
    return {
      code,
      name: found.name || code,
      symbol: found.symbol || code,
    };
  }
  return {
    code,
    name: code,
    symbol: code,
  };
}

export interface TimezoneOption {
  value: string;
  label: string;
  offset: string;
}

export interface TimezoneGroup {
  region: string;
  options: { value: string; label: string }[];
}

export function getTimezonesForCountryCode(countryCode?: string | null): TimezoneOption[] {
  if (!countryCode) return [];
  const list = getTimezonesForCountry(countryCode.trim().toUpperCase()) || [];
  return list.map((t) => ({
    value: t.name,
    label: `${t.name} (UTC${t.utcOffsetStr})`,
    offset: t.utcOffsetStr,
  }));
}

export function getAllTimezonesList(): TimezoneOption[] {
  const all = getAllTimezones();
  return Object.values(all)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((t) => ({
      value: t.name,
      label: `${t.name} (UTC${t.utcOffsetStr})`,
      offset: t.utcOffsetStr,
    }));
}

export function getTimezoneGroupsForCountry(countryCode?: string | null, countryName?: string): TimezoneGroup[] {
  const countryTzs = getTimezonesForCountryCode(countryCode);
  const allTzs = getAllTimezonesList();
  const groups: TimezoneGroup[] = [];

  if (countryTzs.length > 0) {
    groups.push({
      region: `${countryName || countryCode || 'Country'} Timezones`,
      options: countryTzs.map((t) => ({ value: t.value, label: t.label })),
    });
  }

  groups.push({
    region: 'All Worldwide Timezones',
    options: allTzs.map((t) => ({ value: t.value, label: t.label })),
  });

  return groups;
}
