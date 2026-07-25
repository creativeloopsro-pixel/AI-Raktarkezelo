import { ChangeEvent, DragEvent, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileCheck2, FileText, ShieldCheck, UploadCloud, X } from "lucide-react";

import { uploadDocument } from "../lib/api";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const acceptedTypes = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/tiff"
];

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentUploadDialog({ open, onOpenChange }: Props) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState("");

  const mutation = useMutation({
    mutationFn: (selectedFile: File) => uploadDocument(selectedFile),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents"] }),
        queryClient.invalidateQueries({ queryKey: ["review-tasks"] })
      ]);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onOpenChange(false);
    }
  });

  function selectFile(selectedFile?: File) {
    mutation.reset();
    setLocalError("");
    if (!selectedFile) return;
    if (!acceptedTypes.includes(selectedFile.type)) {
      setLocalError("Csak PDF, JPG, PNG vagy TIFF dokumentum választható.");
      return;
    }
    if (selectedFile.size > 25 * 1024 * 1024) {
      setLocalError("A dokumentum legfeljebb 25 MB lehet.");
      return;
    }
    setFile(selectedFile);
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen && !mutation.isPending) {
      setFile(null);
      setLocalError("");
      mutation.reset();
      if (inputRef.current) inputRef.current.value = "";
    }
    onOpenChange(nextOpen);
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content upload-dialog">
          <div className="dialog-heading">
            <div className="dialog-icon">
              <UploadCloud aria-hidden="true" />
            </div>
            <div>
              <Dialog.Title>Dokumentum feltöltése</Dialog.Title>
              <Dialog.Description>
                Szállítólevél, bevételi bizonylat vagy áruátvételi kép.
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-button" aria-label="Bezárás">
              <X aria-hidden="true" />
            </Dialog.Close>
          </div>

          <button
            type="button"
            className={`drop-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            {file ? (
              <>
                <FileCheck2 aria-hidden="true" />
                <strong>{file.name}</strong>
                <span>{formatBytes(file.size)} · feltöltésre kész</span>
              </>
            ) : (
              <>
                <FileText aria-hidden="true" />
                <strong>Húzd ide a dokumentumot</strong>
                <span>vagy kattints a fájl kiválasztásához</span>
              </>
            )}
          </button>
          <input
            ref={inputRef}
            className="sr-only"
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff"
            onChange={handleInput}
          />

          <div className="upload-safety">
            <ShieldCheck aria-hidden="true" />
            <span>
              Tartalomalapú fájlellenőrzés, SHA-256 duplikációvédelem és opcionális
              vírusvizsgálat.
            </span>
          </div>

          {(localError || mutation.error) && (
            <p className="form-error">
              {localError || mutation.error?.message || "A feltöltés sikertelen."}
            </p>
          )}

          <div className="dialog-actions">
            <Dialog.Close className="secondary-button" type="button">
              Mégse
            </Dialog.Close>
            <button
              className="primary-button"
              type="button"
              disabled={!file || mutation.isPending}
              onClick={() => file && mutation.mutate(file)}
            >
              {mutation.isPending ? "Ellenőrzés és feltöltés…" : "Dokumentum feltöltése"}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
