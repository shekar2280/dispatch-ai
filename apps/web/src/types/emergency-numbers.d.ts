declare module "emergency-numbers" {
  export enum NumberType {
    FIRE = "fire",
    POLICE = "police",
    AMBULANCE = "ambulance",
  }

  export interface EmergencyNumbers {
    fire: number | string;
    police: number | string;
    ambulance: number | string;
  }

  export function getEmergencyNumberByCountry(
    countryCode: string,
  ): EmergencyNumbers;
  export function getEmergencyNumberByCountryAndType(
    countryCode: string,
    type: NumberType,
  ): number | string;
  export function getSupportedCountries(): string[];
}

declare module "emergency-numbers/dist/metadata.js" {
  import { EmergencyNumbers } from "emergency-numbers";
  const metadata: Record<string, EmergencyNumbers>;
  export default metadata;
}
