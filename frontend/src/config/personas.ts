/**
 * Demo customers. The backend picks a simulator user per persona (`/v1/demo/{typology}?persona=`): the usual
 * payment amount and touch baselines come from that user, so the same scam scales to each person's money.
 * Names, places and relatives here are the story layer only.
 */
export type PersonaId = "senior" | "student" | "professional";

export interface Persona {
  /** a demo persona, or "custom" for a fleet / builder customer */
  id: PersonaId | "custom";
  name: string;
  initials: string;
  first: string;
  about: string;
  pronoun: { they: string; them: string; their: string };
  /** relative whose voice is cloned, and how they address the customer */
  kin: { clone: string; address: string; hospital: string };
}

export const PERSONAS: Persona[] = [
  {
    id: "senior",
    name: "Harjeet Singh",
    initials: "HS",
    first: "Harjeet",
    about: "67 · farmer, Punjab",
    pronoun: { they: "he", them: "him", their: "his" },
    kin: { clone: "grandson", address: "Dadaji", hospital: "son" },
  },
  {
    id: "student",
    name: "Riya Sharma",
    initials: "RS",
    first: "Riya",
    about: "21 · student, Chandigarh",
    pronoun: { they: "she", them: "her", their: "her" },
    kin: { clone: "younger brother", address: "Didi", hospital: "father" },
  },
  {
    id: "professional",
    name: "Vikram Rao",
    initials: "VR",
    first: "Vikram",
    about: "34 · software engineer, Gurugram",
    pronoun: { they: "he", them: "him", their: "his" },
    kin: { clone: "nephew", address: "Chachu", hospital: "wife" },
  },
];

export const PERSONA_BY_ID = Object.fromEntries(PERSONAS.map((p) => [p.id, p])) as Record<PersonaId, Persona>;

/** Fill {name} {first} {they} {them} {their} {They} {Their} {clone} {address} {hospital} in story text. */
export function personalise(text: string, p: Persona) {
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
  return text.replace(/\{(\w+)\}/g, (m, k: string) => {
    switch (k) {
      case "name": return p.name;
      case "first": return p.first;
      case "they": return p.pronoun.they;
      case "They": return cap(p.pronoun.they);
      case "them": return p.pronoun.them;
      case "their": return p.pronoun.their;
      case "Their": return cap(p.pronoun.their);
      case "clone": return p.kin.clone;
      case "address": return p.kin.address;
      case "hospital": return p.kin.hospital;
      default: return m;
    }
  });
}

/** A customer with no story persona (fleet wall, builder): neutral pronouns, described by the profile. */
export function customPersona(label: string, about: string): Persona {
  return {
    id: "custom",
    name: label,
    initials: label.replace(/[^A-Z0-9]/g, "").slice(0, 2) || "C",
    first: label,
    about,
    pronoun: { they: "they", them: "them", their: "their" },
    kin: { clone: "relative", address: "Hello", hospital: "relative" },
  };
}
