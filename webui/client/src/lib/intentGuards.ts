/**
 * Determines if a message should skip intent classification.
 * Returns true if message should NOT be classified.
 */
export function shouldSkipClassification(message: string): boolean {
  const trimmed = message.trim();

  // Too short
  if (trimmed.length < 10) return true;

  // Slash commands — already have explicit intent
  if (trimmed.startsWith('/')) return true;

  // Questions (starts with question word or ends with ?)
  const questionPattern = /^(what|when|where|who|why|how|can|could|would|should|is|are|do|does|did)\b/i;
  if (questionPattern.test(trimmed) || trimmed.endsWith('?')) return true;

  // Greetings
  const greetings = /^(hi|hello|hey|thanks|thank you|ok|okay|sure|yes|no|bye|good morning|good evening)\b/i;
  if (greetings.test(trimmed)) return true;

  return false;
}
