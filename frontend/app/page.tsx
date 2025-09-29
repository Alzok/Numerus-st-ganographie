"use client";

import React from "react";
import { Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ToastProvider, useToast } from "@/components/ui/use-toast";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const SEED_STORAGE_KEY = "wm-seed";
const BLOCK_OPTIONS = [8, 12, 16];
const STRENGTH_MIN = 0.1;
const STRENGTH_MAX = 2.0;
const DEFAULT_MESSAGE = "Bonjour, ceci est un filigrane robuste.";
const MESSAGE_LIMIT = 4096;

const textEncoder = new TextEncoder();

function countMessageBytes(value: string): number {
  return textEncoder.encode(value).length;
}

function clampToByteLimit(value: string, maxBytes: number): string {
  if (maxBytes <= 0) {
    return "";
  }
  let total = 0;
  let result = "";
  for (const char of value) {
    const size = textEncoder.encode(char).length;
    if (total + size > maxBytes) {
      break;
    }
    result += char;
    total += size;
  }
  return result;
}

function resolveApiBase() {
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    const port = process.env.NEXT_PUBLIC_API_PORT ?? "8080";
    return `${protocol}//${hostname}:${port}`;
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://backend:8080";
}

type Mode = "embed" | "extract";

type EmbedOutcome = {
  filename: string;
  blob: Blob;
  mime: string;
  psnr?: number;
  pageCount?: number;
};

type ExtractOutcome = {
  message: string;
  confidence: number;
  pageIndex: number;
};

type CapacityInfo = {
  capacityBits: number;
  maxMessageBytes: number;
  replicationFactor: number;
  width: number;
  height: number;
};

function base64ToBlob(base64: string, mime: string) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: mime });
}

function formatConfidence(value: number) {
  return `${Math.round(value * 1000) / 10}%`;
}

function formatPSNR(psnr?: number) {
  if (psnr === undefined || Number.isNaN(psnr)) {
    return "--";
  }
  return `${psnr.toFixed(2)} dB`;
}

function Content() {
  const { toast } = useToast();
  const [mode, setMode] = React.useState<Mode>("embed");
  const [message, setMessage] = React.useState(DEFAULT_MESSAGE);
  const [messageBytes, setMessageBytes] = React.useState(() => countMessageBytes(DEFAULT_MESSAGE));
  const [seed, setSeed] = React.useState<number>(() => {
    if (typeof window === "undefined") return Math.floor(Math.random() * 10_000_000);
    const stored = window.localStorage.getItem(SEED_STORAGE_KEY);
    return stored ? Number.parseInt(stored, 10) : Math.floor(Math.random() * 10_000_000);
  });
  const [strength, setStrength] = React.useState(0.5);
  const [blockSize, setBlockSize] = React.useState(8);
  const [file, setFile] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [embedResult, setEmbedResult] = React.useState<EmbedOutcome | null>(null);
  const [extractResult, setExtractResult] = React.useState<ExtractOutcome | null>(null);
  const [formatHint, setFormatHint] = React.useState<string | null>(null);
  const [capacityInfo, setCapacityInfo] = React.useState<CapacityInfo | null>(null);
  const [capacityError, setCapacityError] = React.useState<string | null>(null);
  const [isCapacityLoading, setIsCapacityLoading] = React.useState(false);
  const [wasClamped, setWasClamped] = React.useState(false);
  const capacityRequestId = React.useRef(0);

  const maxMessageBytes = capacityInfo?.maxMessageBytes ?? null;
  const messageLimit = maxMessageBytes ?? MESSAGE_LIMIT;
  const isCapacityZero = maxMessageBytes === 0;
  const isAtByteLimit = capacityInfo ? messageBytes === capacityInfo.maxMessageBytes : false;

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SEED_STORAGE_KEY, String(seed));
  }, [seed]);

  React.useEffect(() => {
    setMessageBytes(countMessageBytes(message));
  }, [message]);

  React.useEffect(() => {
    if (maxMessageBytes == null) {
      setWasClamped(false);
      return;
    }
    setMessage((current) => {
      const clamped = clampToByteLimit(current, maxMessageBytes);
      setWasClamped(clamped !== current);
      return clamped;
    });
  }, [maxMessageBytes]);

  const resetResults = () => {
    setEmbedResult(null);
    setExtractResult(null);
  };

  const fetchCapacity = React.useCallback(
    async (targetFile: File, selectedBlockSize: number) => {
      const requestId = capacityRequestId.current + 1;
      capacityRequestId.current = requestId;
      setIsCapacityLoading(true);
      setCapacityError(null);

      const formData = new FormData();
      formData.append("image", targetFile);
      formData.append("block_size", String(selectedBlockSize));

      try {
        const response = await fetch(`${resolveApiBase()}/embed/capacity`, {
          method: "POST",
          headers: {
            Accept: "application/json",
          },
          body: formData,
        });
        const payload = await response.json().catch(() => null);

        if (capacityRequestId.current !== requestId) {
          return;
        }

        if (!response.ok) {
          const detail =
            payload && typeof payload.detail === "string"
              ? payload.detail
              : "Impossible d'évaluer la capacité du support.";
          throw new Error(detail);
        }

        setCapacityInfo({
          capacityBits: Number(payload.capacity_bits ?? 0),
          maxMessageBytes: Number(payload.max_message_bytes ?? 0),
          replicationFactor: Number(payload.replication_factor ?? 1),
          width: Number(payload.width ?? 0),
          height: Number(payload.height ?? 0),
        });
        setCapacityError(null);
      } catch (error) {
        if (capacityRequestId.current !== requestId) {
          return;
        }
        setCapacityInfo(null);
        setCapacityError(
          error instanceof Error
            ? error.message
            : "Impossible d'évaluer la capacité du support."
        );
        setWasClamped(false);
      } finally {
        if (capacityRequestId.current === requestId) {
          setIsCapacityLoading(false);
        }
      }
    },
    []
  );

  const handleMessageInput = React.useCallback(
    (value: string) => {
      if (capacityInfo) {
        const limited = clampToByteLimit(value, capacityInfo.maxMessageBytes);
        setWasClamped(limited !== value);
        setMessage(limited);
        return;
      }
      setWasClamped(false);
      setMessage(value);
    },
    [capacityInfo]
  );

  const onFileChange = (targetFile: File | null) => {
    setFile(targetFile);
    resetResults();
    if (!targetFile) {
      setPreviewUrl(null);
      setFormatHint(null);
      setCapacityInfo(null);
      setCapacityError(null);
      setIsCapacityLoading(false);
      setWasClamped(false);
      return;
    }

    setCapacityError(null);
    setCapacityInfo(null);
    setIsCapacityLoading(true);
    setWasClamped(false);

    if (targetFile.type === "application/pdf") {
      setFormatHint("PDF importé : chaque page sera convertie et filigranée individuellement.");
      setPreviewUrl(null);
    } else {
      const objectUrl = URL.createObjectURL(targetFile);
      setPreviewUrl(objectUrl);
      if (targetFile.type === "image/png") {
        setFormatHint(null);
      } else {
        setFormatHint("Suggestion : exportez en PNG pour éviter les pertes de qualité.");
      }
    }

    fetchCapacity(targetFile, blockSize);
  };

  React.useEffect(() => {
    if (!file) return;
    fetchCapacity(file, blockSize);
  }, [blockSize, file, fetchCapacity]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      toast({
        title: "Aucun fichier",
        description: "Ajoutez une image ou un PDF avant de lancer l'opération.",
        variant: "destructive",
      });
      return;
    }

    if (mode === "embed" && capacityInfo && capacityInfo.maxMessageBytes === 0) {
      toast({
        title: "Capacité insuffisante",
        description: "Cette image est trop petite pour accueillir un message.",
        variant: "destructive",
      });
      return;
    }

    const formData = new FormData();
    formData.append("image", file);
    formData.append("seed", String(seed));
    formData.append("block_size", String(blockSize));

    const apiBase = resolveApiBase();
    let url = `${apiBase}/embed`;
    if (mode === "embed") {
      formData.append("message", message);
      formData.append("strength", String(strength));
    } else {
      url = `${apiBase}/extract`;
    }

    try {
      setIsLoading(true);
      const response = await fetch(url, {
        method: "POST",
        headers: {
          Accept: "application/json",
        },
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Erreur serveur" }));
        throw new Error(error.detail ?? "Impossible de traiter la requête");
      }

      const data = await response.json();

      if (mode === "embed") {
        const blob = data.file_base64
          ? base64ToBlob(data.file_base64, data.mime)
          : new Blob([], { type: data.mime });
        setEmbedResult({
          filename: data.filename ?? "watermarked",
          blob,
          mime: data.mime ?? "image/png",
          psnr: data.psnr,
          pageCount: data.page_count,
        });
        setExtractResult(null);
        toast({
          title: "Intégration réussie",
          description: "Le filigrane a été inscrit dans le fichier.",
        });
      } else {
        setExtractResult({
          message: data.message ?? "",
          confidence: Number(data.confidence ?? 0),
          pageIndex: Number(data.page_index ?? 0),
        });
        setEmbedResult(null);
        toast({
          title: "Extraction terminée",
          description: "Le message caché a été récupéré.",
        });
      }
    } catch (error) {
      toast({
        title: "Opération échouée",
        description: error instanceof Error ? error.message : "Erreur inconnue",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const triggerDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = () => {
    if (!extractResult) return;
    navigator.clipboard.writeText(extractResult.message).then(() => {
      toast({
        title: "Copié",
        description: "Le message extrait est dans le presse-papiers.",
      });
    });
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 pb-16">
      <div className="pointer-events-none absolute inset-0 opacity-60">
        <div className="absolute -left-24 top-28 h-72 w-72 rounded-full bg-sky-500/25 blur-3xl" />
        <div className="absolute -right-24 top-60 h-80 w-80 rounded-full bg-blue-700/25 blur-3xl" />
      </div>

      <div className="relative mx-auto flex w-full max-w-6xl flex-col gap-12 px-4 pt-16 md:flex-row md:items-start md:gap-10 md:px-10">
        <aside className="flex w-full flex-col gap-8 md:w-[32%]">
          <Card className="border border-border/40 bg-secondary/20 p-0 shadow-[0_30px_90px_-45px_rgba(56,189,248,0.45)] backdrop-blur">
            <CardContent className="flex flex-col gap-6 p-8">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="border-sky-400/60 text-sky-200">
                  Suite locale – Encryption Light
                </Badge>
              </div>
              <h1 className="text-3xl font-semibold tracking-tight text-white md:text-[2.6rem]">
                Filigrane fréquentiel nouvelle génération
              </h1>
              <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
                Intégrez ou extrayez un message robuste dans vos images et PDF sans quitter votre machine. Chaque action est traitée en local, sans fuite de données.
              </p>
              <div className="grid gap-3 rounded-2xl border border-border/40 bg-background/35 p-4 text-sm text-muted-foreground">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs uppercase tracking-wide text-muted-foreground/70">Formats pris en charge</span>
                  <Badge variant="outline" className="bg-secondary/40">
                    PNG · JPG · WebP · PDF
                  </Badge>
                </div>
                <Separator />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs uppercase tracking-wide text-muted-foreground/70">Capacité maximale</span>
                  <Badge variant="outline" className="bg-secondary/40">
                    4096 octets / message
                  </Badge>
                </div>
                <Separator />
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs uppercase tracking-wide text-muted-foreground/70">Robustesse</span>
                  <Badge variant="outline" className="bg-secondary/40">
                    Réplique ×3 · CRC32
                  </Badge>
                </div>
              </div>
              <Separator className="opacity-50" />
              <div className="flex flex-wrap items-center gap-4 text-[0.7rem] tracking-wide text-muted-foreground/70">
                <span className="flex items-center gap-2">
                  <span className="inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" /> Temps réel Next.js · FastAPI (timeout 15 s)
                </span>
                <span className="flex items-center gap-2">
                  <span className="inline-flex h-1.5 w-1.5 rounded-full bg-sky-400" /> JPEG quali ≥ 85 conseillé · PDF ≤ 10 pages
                </span>
              </div>
            </CardContent>
          </Card>

          <Card className="border border-border/40 bg-secondary/25 p-0 shadow-[0_20px_80px_-55px_rgba(59,130,246,0.55)]">
            <CardHeader className="flex flex-col gap-2 p-6 pb-3">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold tracking-tight text-white">Aperçu</h2>
                <div className="flex flex-wrap items-center gap-2">
                  {embedResult?.psnr ? <Badge>PSNR {formatPSNR(embedResult.psnr)}</Badge> : null}
                  {extractResult ? (
                    <Badge>
                      Page {extractResult.pageIndex + 1} • Confiance {formatConfidence(extractResult.confidence)}
                    </Badge>
                  ) : null}
                </div>
              </div>
              <p className="text-xs text-muted-foreground">Visualisez le support sélectionné et téléchargez le fichier intégré.</p>
            </CardHeader>
            <CardContent className="p-6 pt-0">
              <div className="flex min-h-[220px] items-center justify-center overflow-hidden rounded-2xl border border-border/40 bg-background/40">
                {previewUrl ? (
                  <img src={previewUrl} alt="Prévisualisation" className="h-full w-full object-contain" />
                ) : file?.type === "application/pdf" ? (
                  <div className="flex max-w-xs flex-col items-center gap-3 text-center text-sm text-muted-foreground">
                    <svg className="h-12 w-12 text-accent" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                      <path d="M7 3h6l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
                      <path d="M13 3v5h5" />
                    </svg>
                    <p>Prévisualisation PDF indisponible. Téléchargez le résultat pour le consulter.</p>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Importez un fichier pour afficher l'aperçu.</p>
                )}
              </div>
            </CardContent>
            {embedResult ? (
              <CardFooter className="flex flex-wrap items-center gap-3 p-6 pt-0">
                <Button
                  type="button"
                  variant="secondary"
                  className="rounded-xl px-5"
                  onClick={() => triggerDownload(embedResult.blob, embedResult.filename)}
                >
                  Télécharger ({embedResult.mime.split("/")[1]?.toUpperCase() ?? "fichier"})
                </Button>
                {embedResult.pageCount ? (
                  <p className="text-xs text-muted-foreground">{embedResult.pageCount} page(s) filigranée(s)</p>
                ) : null}
              </CardFooter>
            ) : null}
          </Card>
        </aside>

        <main className="flex w-full flex-col gap-8 md:flex-1">
          <Card className="border border-border/50 bg-secondary/25 p-0 shadow-[0_20px_90px_-55px_rgba(94,234,212,0.35)]">
            <CardHeader className="flex flex-wrap items-center justify-between gap-4 p-6 pb-4">
              <div className="inline-flex rounded-2xl bg-background/40 p-1.5">
                <Button
                  type="button"
                  className="rounded-xl px-5"
                  variant={mode === "embed" ? "default" : "secondary"}
                  onClick={() => {
                    setMode("embed");
                    resetResults();
                  }}
                >
                  Intégrer
                </Button>
                <Button
                  type="button"
                  className="rounded-xl px-5"
                  variant={mode === "extract" ? "default" : "secondary"}
                  onClick={() => {
                    setMode("extract");
                    resetResults();
                  }}
                >
                  Extraire
                </Button>
              </div>
              {isLoading ? (
                <div className="flex items-center gap-3 rounded-2xl bg-background/40 px-4 py-2 text-sm text-muted-foreground">
                  <Spinner className="h-4 w-4" /> Traitement en cours…
                </div>
              ) : null}
            </CardHeader>
            <CardContent className="p-6 pt-0">
              <form className="flex flex-col gap-8" onSubmit={handleSubmit}>
                <div className="grid gap-4">
                  <Label htmlFor="file">Fichier source</Label>
                  <label
                    className={cn(
                      "relative flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border/50 bg-secondary/20 px-6 py-10 text-center transition hover:border-primary/60 hover:bg-secondary/30",
                      file ? "border-primary/60 bg-secondary/30" : undefined
                    )}
                    htmlFor="file"
                  >
                    <span className="text-sm font-semibold text-muted-foreground">
                      Glissez-déposez vos images (PNG, JPG, WebP) ou PDF (≤ 10 Mo)
                    </span>
                    <span className="text-xs text-muted-foreground/80">
                      {file ? file.name : "Aucun fichier sélectionné"}
                    </span>
                    <Input
                      className="hidden"
                      id="file"
                      type="file"
                      accept="image/png,image/jpeg,image/webp,application/pdf"
                      onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
                    />
                  </label>
                  {formatHint ? <p className="text-xs text-accent">{formatHint}</p> : null}
                </div>

                {mode === "embed" ? (
                  <div className="grid gap-4">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="message">Message à dissimuler</Label>
                      <Badge variant="outline" className="bg-background/40 font-normal">
                        {messageBytes} / {messageLimit} octet(s)
                      </Badge>
                    </div>
                    <Textarea
                      id="message"
                      placeholder="Saisissez votre message secret"
                      value={message}
                      onChange={(event) => handleMessageInput(event.target.value)}
                      rows={4}
                      required
                    />
                    <div className="space-y-2 text-xs">
                      {isCapacityLoading ? (
                        <p className="rounded-xl bg-secondary/30 px-4 py-2 text-muted-foreground">
                          Calcul de la capacité…
                        </p>
                      ) : capacityError ? (
                        <p className="rounded-xl bg-red-500/10 px-4 py-2 text-destructive">{capacityError}</p>
                      ) : capacityInfo ? (
                        <div className="grid gap-2 rounded-xl border border-border/40 bg-background/40 p-4 text-muted-foreground">
                          <div className="flex items-center justify-between gap-3">
                            <span>Capacité disponible</span>
                            <Badge variant="outline" className="bg-secondary/40">
                              {capacityInfo.maxMessageBytes} octet(s)
                            </Badge>
                          </div>
                          <Separator />
                          <div className="flex items-center justify-between gap-3 text-[0.7rem] uppercase tracking-wide text-muted-foreground/70">
                            <span>Dimensions traitées</span>
                            <span>
                              {capacityInfo.width} × {capacityInfo.height} px
                            </span>
                          </div>
                          <Separator />
                          <div className="flex items-center justify-between gap-3">
                            <span>Message actuel</span>
                            <Badge variant="outline" className="bg-secondary/30">
                              {messageBytes} octet(s)
                            </Badge>
                          </div>
                        </div>
                      ) : file ? (
                        <p className="rounded-xl bg-secondary/30 px-4 py-2 text-muted-foreground">
                          Capacité en cours d'évaluation…
                        </p>
                      ) : (
                        <p className="rounded-xl bg-background/40 px-4 py-2 text-muted-foreground">
                          Importez un fichier pour calculer la capacité disponible.
                        </p>
                      )}
                      {wasClamped && !isCapacityLoading && !capacityError ? (
                        <p className="rounded-full bg-blue-500/15 px-4 py-1.5 text-center text-sky-200">
                          Le message a été ajusté pour respecter la limite de capacité.
                        </p>
                      ) : null}
                      {isCapacityZero && !isCapacityLoading && !capacityError ? (
                        <p className="rounded-full bg-red-500/15 px-4 py-1.5 text-center text-destructive">
                          L'image sélectionnée est trop petite. Choisissez un support plus grand.
                        </p>
                      ) : null}
                      {isAtByteLimit && !isCapacityZero && !isCapacityLoading && !capacityError ? (
                        <p className="rounded-full bg-emerald-500/15 px-4 py-1.5 text-center text-emerald-200">
                          Capacité maximale atteinte. Ajoutez une image plus grande pour davantage de texte.
                        </p>
                      ) : null}
                    </div>
                  </div>
                ) : null}

                <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="seed">Seed</Label>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            type="button"
                            className="rounded-full p-1 text-muted-foreground transition hover:text-foreground"
                            aria-label="Informations sur la seed"
                          >
                            <Info className="h-4 w-4" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>
                          Grâce à la seed, le placement des bits est pseudo-aléatoire. Utilisez la même valeur pour extraire le message.
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    <Input
                      id="seed"
                      type="number"
                      value={seed}
                      min={0}
                      onChange={(event) => setSeed(Number(event.target.value))}
                      required
                    />
                  </div>
                  {mode === "embed" ? (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="strength">Strength</Label>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              className="rounded-full p-1 text-muted-foreground transition hover:text-foreground"
                              aria-label="Informations sur la strength"
                            >
                              <Info className="h-4 w-4" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>
                            Intensité de la modification des coefficients DCT. Plus fort = extraction plus robuste mais risque de baisse du PSNR.
                          </TooltipContent>
                        </Tooltip>
                      </div>
                      <Input
                        id="strength"
                        type="number"
                        step="0.1"
                        min={STRENGTH_MIN}
                        max={STRENGTH_MAX}
                        value={strength}
                        onChange={(event) => setStrength(Number(event.target.value))}
                      />
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">&nbsp;</Label>
                      <div className="rounded-xl border border-border/50 bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
                        Strength utilisée côté serveur.
                      </div>
                    </div>
                  )}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="blockSize">Bloc</Label>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button
                            type="button"
                            className="rounded-full p-1 text-muted-foreground transition hover:text-foreground"
                            aria-label="Informations sur la taille de bloc"
                          >
                            <Info className="h-4 w-4" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>
                          Taille des blocs appliqués sur la sous-bande LL. Des blocs plus grands offrent plus de capacité mais réagissent différemment aux attaques.
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    <Select
                      id="blockSize"
                      value={String(blockSize)}
                      onChange={(event) => setBlockSize(Number(event.target.value))}
                    >
                      {BLOCK_OPTIONS.map((size) => (
                        <option key={size} value={String(size)}>
                          {size}
                        </option>
                      ))}
                    </Select>
                  </div>
                </div>

                <Button
                  type="submit"
                  className="self-start rounded-xl px-6 py-2.5 shadow-[0_18px_40px_-28px_rgba(59,130,246,0.75)]"
                  disabled={isLoading || (mode === "embed" && (isCapacityLoading || isCapacityZero))}
                >
                  {mode === "embed" ? "Lancer l'intégration" : "Lancer l'extraction"}
                </Button>
              </form>
            </CardContent>
          </Card>

          {extractResult ? (
            <Card className="border border-border/50 bg-secondary/20 p-0 shadow-[0_18px_60px_-50px_rgba(94,234,212,0.35)]">
              <CardHeader className="flex flex-col gap-2 p-6 pb-3">
                <h2 className="text-lg font-semibold tracking-tight text-white">Message extrait</h2>
                <p className="text-xs text-muted-foreground">
                  Page {extractResult.pageIndex + 1} • Confiance {formatConfidence(extractResult.confidence)}
                </p>
              </CardHeader>
              <CardContent className="p-6 pt-0">
                <pre className="max-h-[220px] overflow-auto whitespace-pre-wrap rounded-2xl border border-border/40 bg-background/40 px-5 py-4 text-sm text-muted-foreground">
                  {extractResult.message}
                </pre>
              </CardContent>
              <CardFooter className="flex items-center justify-end gap-3 p-6 pt-0">
                <Button type="button" variant="secondary" className="rounded-xl px-5" onClick={handleCopy}>
                  Copier le message
                </Button>
              </CardFooter>
            </Card>
          ) : null}
        </main>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <ToastProvider>
      <TooltipProvider delayDuration={150} skipDelayDuration={200}>
        <Content />
      </TooltipProvider>
    </ToastProvider>
  );
}
