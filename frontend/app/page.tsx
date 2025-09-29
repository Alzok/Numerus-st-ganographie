"use client";

import React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ToastProvider, useToast } from "@/components/ui/use-toast";
import { cn } from "@/lib/utils";

const DEFAULT_MESSAGE = "Bonjour, ceci est un filigrane robuste.";

const textEncoder = new TextEncoder();

function countMessageBytes(value: string): number {
  return textEncoder.encode(value).length;
}

function resolveApiBase() {
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    const port = process.env.NEXT_PUBLIC_API_PORT ?? "8080";
    return `${protocol}//${hostname}:${port}`;
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://backend:8080";
}

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

function formatPSNR(psnr?: number | null) {
  if (psnr == null || Number.isNaN(psnr)) return "--";
  return `${psnr.toFixed(2)} dB`;
}

type Mode = "embed" | "extract";

type EmbedOutcome = {
  filename: string;
  blob: Blob;
  mime: string;
  psnr?: number | null;
  pageCount?: number;
  pdfBlob?: Blob;
  pdfFilename?: string;
  pdfMime?: string;
};

type ExtractOutcome = {
  message: string;
  confidence: number;
  pageIndex: number;
};

function Content() {
  const { toast } = useToast();
  const [mode, setMode] = React.useState<Mode>("embed");
  const [message, setMessage] = React.useState(DEFAULT_MESSAGE);
  const [messageBytes, setMessageBytes] = React.useState(() => countMessageBytes(DEFAULT_MESSAGE));
  const [file, setFile] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [embedResult, setEmbedResult] = React.useState<EmbedOutcome | null>(null);
  const [extractResult, setExtractResult] = React.useState<ExtractOutcome | null>(null);
  const [formatHint, setFormatHint] = React.useState<string | null>(null);
  React.useEffect(() => {
    setMessageBytes(countMessageBytes(message));
  }, [message]);

  const resetResults = () => {
    setEmbedResult(null);
    setExtractResult(null);
  };

  const handleMessageInput = React.useCallback(
    (value: string) => {
      setMessage(value);
    },
    []
  );

  const onFileChange = (targetFile: File | null) => {
    setFile(targetFile);
    resetResults();
    if (!targetFile) {
      setPreviewUrl(null);
      setFormatHint(null);
      return;
    }

    if (targetFile.type === "application/pdf") {
      setFormatHint("PDF importé : chaque page sera convertie et filigranée individuellement.");
      setPreviewUrl(null);
    } else {
      const objectUrl = URL.createObjectURL(targetFile);
      setPreviewUrl(objectUrl);
      setFormatHint(
        targetFile.type === "image/png"
          ? null
          : "Suggestion : exportez en PNG pour éviter les pertes de qualité."
      );
    }

  };

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

    const formData = new FormData();
    formData.append("image", file);
    if (mode === "embed") {
      const trimmed = message.trim();
      if (!trimmed) {
        toast({
          title: "Message manquant",
          description: "Saisissez un message avant d'intégrer le filigrane.",
          variant: "destructive",
        });
        return;
      }
      formData.append("message", trimmed);
    }

    const apiBase = resolveApiBase();
    const url = `${apiBase}/${mode === "embed" ? "embed" : "extract"}`;

    try {
      setIsLoading(true);
      const response = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Erreur serveur" }));
        throw new Error(error.detail ?? "Impossible de traiter la requête");
      }

      const data = await response.json();

      if (mode === "embed") {
        const primaryMime: string = data.mime ?? data.pdf_mime ?? "image/png";
        const primaryBase = file.name?.split(".")[0] ?? "watermarked";
        const primaryFilename: string = data.filename ?? `${primaryBase}.${primaryMime.split("/")[1] ?? "png"}`;

        let primaryBlob: Blob | null = null;
        if (data.file_base64) {
          primaryBlob = base64ToBlob(data.file_base64, primaryMime);
        }

        let pdfBlob: Blob | undefined;
        let pdfFilename: string | undefined;
        let pdfMime: string | undefined;
        if (data.pdf_base64) {
          pdfMime = data.pdf_mime ?? "application/pdf";
          pdfFilename = data.pdf_filename ?? `${primaryBase}.pdf`;
          pdfBlob = base64ToBlob(data.pdf_base64, pdfMime);
        }

        const blob = primaryBlob ?? pdfBlob ?? new Blob([], { type: primaryMime });

        setEmbedResult({
          filename: primaryFilename,
          blob,
          mime: primaryMime,
          psnr: data.psnr ?? null,
          pageCount: data.page_count,
          pdfBlob,
          pdfFilename,
          pdfMime,
        });
        setExtractResult(null);
        toast({
          title: "Intégration réussie",
          description: "Le texte a été intégré sous forme de calque invisible.",
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
          <div className="rounded-3xl border border-border/40 bg-secondary/20 p-5 shadow-[0_30px_90px_-45px_rgba(56,189,248,0.45)] backdrop-blur">
            <div className="space-y-2">
              <h1 className="text-2xl font-semibold tracking-tight text-white">Watermark Tool</h1>
              <p className="text-sm text-muted-foreground">
                Filigrane invisible hors ligne : message injecté dans les métadonnées et dupliqué par un calque imperceptible.
              </p>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3 text-xs uppercase tracking-wide text-muted-foreground/70">
              <span className="flex items-center gap-2">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-sky-400" /> Formats : PNG · JPG · WebP · PDF
              </span>
              <span className="flex items-center gap-2">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" /> Métadonnées + calque invisible
              </span>
              <span className="flex items-center gap-2">
                <span className="inline-flex h-1.5 w-1.5 rounded-full bg-blue-400" /> Extraction rapide via `/extract`
              </span>
            </div>
          </div>

          <Card className="border border-border/40 bg-secondary/25 p-0 shadow-[0_20px_80px_-55px_rgba(59,130,246,0.55)]">
            <CardHeader className="flex flex-col gap-2 p-6 pb-3">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold tracking-tight text-white">Aperçu</h2>
                <div className="flex flex-wrap items-center gap-2">
                  {embedResult?.psnr != null ? <Badge>PSNR {formatPSNR(embedResult.psnr)}</Badge> : null}
                  {extractResult ? (
                    <Badge>
                      Page {extractResult.pageIndex + 1} • Confiance {formatConfidence(extractResult.confidence)}
                    </Badge>
                  ) : null}
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Visualisez la ressource importée ; le calque caché reste invisible tout en restant récupérable par l'outil.
              </p>
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
                  className="rounded-xl px-4"
                  onClick={() => triggerDownload(embedResult.mime.includes("pdf") ? (embedResult.pdfBlob ?? embedResult.blob) : embedResult.blob, embedResult.mime.includes("pdf") ? (embedResult.pdfFilename ?? embedResult.filename) : embedResult.filename)}
                >
                  Télécharger résultat
                </Button>
                {embedResult.pageCount ? (
                  <p className="text-xs text-muted-foreground">{embedResult.pageCount} page(s)</p>
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
                        {messageBytes} octet(s)
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
                    <div className="space-y-3 text-xs text-muted-foreground">
                      <div className="rounded-xl border border-border/40 bg-background/40 p-4 leading-relaxed">
                        <p>
                          Le texte est appliqué sous forme de calque répété, à très faible opacité, sur toute l'image ou chaque page du PDF.
                        </p>
                        <p className="mt-2 text-[0.7rem] uppercase tracking-wide text-muted-foreground/70">
                          Pas de limite stricte, mais privilégiez des messages courts pour rester discret.
                        </p>
                      </div>
                    </div>

                    <p className="rounded-xl border border-border/40 bg-background/40 p-4 text-xs text-muted-foreground">
                      Le texte invisible est positionné automatiquement avec une police minuscule et une opacité quasi nulle afin qu'il reste imperceptible.
                    </p>
                  </div>
                ) : null}

                <Button
                  type="submit"
                  className="self-start rounded-xl px-6 py-2.5 shadow-[0_18px_40px_-28px_rgba(59,130,246,0.75)]"
                  disabled={isLoading || (mode === "embed" && message.trim().length === 0)}
                >
                  {mode === "embed" ? "Lancer l'intégration" : "Lancer l'extraction"}
                </Button>

                {mode === "embed" && embedResult ? (
                  <div className="rounded-2xl border border-primary/40 bg-primary/5 px-5 py-4 text-sm text-muted-foreground">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <div className="space-y-1">
                        <p className="text-xs uppercase tracking-wide text-primary/90">Fichier prêt</p>
                        <p className="text-sm text-primary/80">
                          {embedResult.mime.includes("pdf") ? "PDF" : "PNG"} prêt à l'envoi
                          {embedResult.psnr != null ? ` • PSNR ${formatPSNR(embedResult.psnr)}` : ""}
                        </p>
                        {embedResult.pageCount ? (
                          <p className="text-xs text-primary/70">{embedResult.pageCount} page(s)</p>
                        ) : null}
                      </div>
                      <Button
                        type="button"
                        className="rounded-xl px-4"
                        onClick={() =>
                          triggerDownload(
                            embedResult.mime.includes("pdf") ? (embedResult.pdfBlob ?? embedResult.blob) : embedResult.blob,
                            embedResult.mime.includes("pdf") ? (embedResult.pdfFilename ?? embedResult.filename) : embedResult.filename,
                          )
                        }
                      >
                        Télécharger {embedResult.mime.includes("pdf") ? "PDF" : "PNG"}
                      </Button>
                    </div>
                  </div>
                ) : null}
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
      <Content />
    </ToastProvider>
  );
}
