import Dexie, { type EntityTable } from "dexie";
import type { ChatMessage, ChatSession } from "@/types/herness";

class HernessDB extends Dexie {
  sessions!: EntityTable<ChatSession, "id">;
  messages!: EntityTable<ChatMessage, "id">;

  constructor() {
    super("herness-console");
    this.version(1).stores({
      sessions: "id, persona, userId, updatedAt",
      messages: "id, sessionId, createdAt",
    });
  }
}

export const db = new HernessDB();

export async function loadSessions(persona?: string): Promise<ChatSession[]> {
  const sessions = persona
    ? await db.sessions.where("persona").equals(persona).toArray()
    : await db.sessions.toArray();
  return sessions.sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

export async function saveSession(session: ChatSession): Promise<void> {
  await db.sessions.put(session);
}

export async function deleteSession(sessionId: string): Promise<void> {
  await db.transaction("rw", db.sessions, db.messages, async () => {
    await db.messages.where("sessionId").equals(sessionId).delete();
    await db.sessions.delete(sessionId);
  });
}

export async function loadMessages(sessionId: string): Promise<ChatMessage[]> {
  const messages = await db.messages
    .where("sessionId")
    .equals(sessionId)
    .toArray();
  return messages.sort(
    (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
  );
}

export async function saveMessage(message: ChatMessage): Promise<void> {
  await db.messages.put(message);
}

export async function updateMessage(message: ChatMessage): Promise<void> {
  await db.messages.put(message);
}

export async function touchSession(
  sessionId: string,
  patch?: Partial<Pick<ChatSession, "title" | "updatedAt">>,
): Promise<void> {
  const session = await db.sessions.get(sessionId);
  if (!session) return;
  await db.sessions.put({
    ...session,
    ...patch,
    updatedAt: patch?.updatedAt ?? new Date().toISOString(),
  });
}

export async function clearMessages(sessionId: string): Promise<void> {
  await db.messages.where("sessionId").equals(sessionId).delete();
}
