import { createClient } from "@supabase/supabase-js";
import type { CoreMessage } from "ai";

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

// Initialize Supabase Client if keys are configured
export const supabase = supabaseUrl && supabaseKey
  ? createClient(supabaseUrl, supabaseKey)
  : null;

/**
 * Loads conversation history for a given chatId from Supabase.
 */
export async function loadChatHistory(chatId: string | number): Promise<CoreMessage[]> {
  if (!supabase) {
    return [];
  }

  try {
    const { data, error } = await supabase
      .from("messages")
      .select("role, content")
      .eq("chat_id", String(chatId))
      .order("created_at", { ascending: true });

    if (error) {
      console.error("Error loading chat history from Supabase:", error);
      return [];
    }

    return (data || []).map((m: any) => ({
      role: m.role as "user" | "assistant" | "system",
      content: m.content,
    }));
  } catch (err) {
    console.error("Supabase load failed:", err);
    return [];
  }
}

/**
 * Saves a single message to Supabase.
 */
export async function saveMessage(
  chatId: string | number,
  role: "user" | "assistant" | "system",
  content: string,
  chatName?: string
): Promise<void> {
  if (!supabase) return;

  try {
    const idStr = String(chatId);

    // Ensure the chat session exists
    const { error: chatError } = await supabase
      .from("chats")
      .upsert({ id: idStr, name: chatName });

    if (chatError) {
      console.error("Error upserting chat session in Supabase:", chatError);
      return;
    }

    // Insert the message
    const { error: msgError } = await supabase
      .from("messages")
      .insert({
        chat_id: idStr,
        role,
        content,
        chat_name: chatName,
      });

    if (msgError) {
      console.error("Error saving message to Supabase:", msgError);
    }
  } catch (err) {
    console.error("Supabase save failed:", err);
  }
}

/**
 * Saves multiple messages to Supabase in a batch.
 */
export async function saveMessages(
  chatId: string | number,
  messages: { role: "user" | "assistant" | "system"; content: string }[],
  chatName?: string
): Promise<void> {
  if (!supabase || messages.length === 0) return;

  try {
    const idStr = String(chatId);

    // Ensure the chat session exists
    const { error: chatError } = await supabase
      .from("chats")
      .upsert({ id: idStr, name: chatName });

    if (chatError) {
      console.error("Error upserting chat session in Supabase:", chatError);
      return;
    }

    // Prepare batch messages
    const records = messages.map((m) => ({
      chat_id: idStr,
      role: m.role,
      content: m.content,
      chat_name: chatName,
    }));

    const { error: msgError } = await supabase
      .from("messages")
      .insert(records);

    if (msgError) {
      console.error("Error batch saving messages to Supabase:", msgError);
    }
  } catch (err) {
    console.error("Supabase batch save failed:", err);
  }
}

/**
 * Creates or updates a chat session with a specific name.
 */
export async function createChat(chatId: string, name: string): Promise<void> {
  if (!supabase) return;

  try {
    const { error } = await supabase
      .from("chats")
      .upsert({ id: chatId, name });

    if (error) {
      console.error("Error creating/updating chat in Supabase:", error);
    }
  } catch (err) {
    console.error("Supabase createChat failed:", err);
  }
}

/**
 * Lists all existing chats ordered by their creation time (newest first).
 */
export async function listChats(): Promise<{ id: string; name: string }[]> {
  if (!supabase) return [];

  try {
    const { data, error } = await supabase
      .from("chats")
      .select("id, name")
      .order("created_at", { ascending: false });

    if (error) {
      console.error("Error listing chats from Supabase:", error);
      return [];
    }

    return (data || []).map((c: any) => ({
      id: c.id,
      name: c.name || c.id,
    }));
  } catch (err) {
    console.error("Supabase listChats failed:", err);
    return [];
  }
}

