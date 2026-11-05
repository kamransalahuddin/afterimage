export type Category = "face" | "email" | "phone" | "address" | "secret" | "card" | "other";

export interface BoxN {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Detection {
  id: string;
  category: Category;
  label: string;
  page: number;
  boxes: BoxN[];
  confidence: number;
  preview: string;
  source: string;
  suggested: boolean;
}

export interface MetadataItem {
  key: string;
  label: string;
  value: string;
}

export interface Analysis {
  session_id: string;
  session_token: string;
  expires_at: string;
  filename: string;
  kind: "image" | "pdf";
  mime: string;
  pages: { width: number; height: number }[];
  detections: Detection[];
  metadata: MetadataItem[];
  notes: string[];
}

export interface ManualRegion extends BoxN {
  id: string;
  page: number;
}

export interface RedactResult {
  artifact_id: string;
  filename: string;
  mime: string;
  size: number;
  sha256: string;
  expires_at: string;
  regions: number;
  metadata_removed: string[];
  verification: {
    text_in_redacted_areas?: number;
    residual_matches?: number;
    regions_verified?: number;
    metadata_stripped?: boolean;
    rasterized?: boolean;
  };
}

export interface ShareCreated {
  id: string;
  url: string;
  token: string;
  manage_token: string;
  expires_at: string;
  max_downloads: number | null;
}

export interface SharePublic {
  filename: string;
  mime: string;
  size: number;
  expires_at: string;
  downloads_remaining: number | null;
}

export const CATEGORY_META: Record<Category, { label: string; order: number }> = {
  face: { label: "Faces", order: 0 },
  email: { label: "Email addresses", order: 1 },
  phone: { label: "Phone numbers", order: 2 },
  address: { label: "Physical addresses", order: 3 },
  secret: { label: "API keys and tokens", order: 4 },
  card: { label: "Credit card numbers", order: 5 },
  other: { label: "Other sensitive text", order: 6 },
};
