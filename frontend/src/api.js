/**
 * API client with defensive error parsing and HTTP wrappers.
 */

async function parseResponse(response) {
  const text = await response.text();
  let data = null;

  if (text && text.trim().length > 0) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const message =
      data?.error?.message ||
      (text && text.length < 200 ? text : `Request failed with status ${response.status}`);
    const code = data?.error?.code || "HTTP_ERROR";
    const err = new Error(message);
    err.code = code;
    err.status = response.status;
    throw err;
  }

  return data;
}

export async function extractDocument(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/extract", {
    method: "POST",
    body: formData,
  });

  return parseResponse(response);
}

export async function getDocuments(status = null, limit = 50, offset = 0) {
  const params = new URLSearchParams();
  if (status && status !== "all") {
    params.set("status", status);
  }
  params.set("limit", String(limit));
  params.set("offset", String(offset));

  const response = await fetch(`/api/documents?${params.toString()}`);
  return parseResponse(response);
}

export async function getDocument(id) {
  const response = await fetch(`/api/documents/${id}`);
  return parseResponse(response);
}

export async function updateDocument(id, data, markReviewed = false) {
  const response = await fetch(`/api/documents/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      data,
      mark_reviewed: markReviewed,
    }),
  });

  return parseResponse(response);
}

export async function reextractDocument(id) {
  const response = await fetch(`/api/documents/${id}/reextract`, {
    method: "POST",
  });

  return parseResponse(response);
}

export async function deleteDocument(id) {
  const response = await fetch(`/api/documents/${id}`, {
    method: "DELETE",
  });

  return parseResponse(response);
}

export async function deleteAllDocuments() {
  const response = await fetch("/api/documents?confirm=true", {
    method: "DELETE",
  });

  return parseResponse(response);
}

