// 本のタイトル・著者の入力の確かめ（手入力で追加・本の情報を編集で使う。screens.md 2.・3.）

import { AUTHOR_MAX, TITLE_MAX } from "../api/books";
import type { ApiError } from "../api/client";
import { countChars } from "../lib/text";

export type BookFormErrors = { title?: string; author?: string };

export function validateBookForm(title: string, author: string): BookFormErrors {
  const errors: BookFormErrors = {};
  if (title === "") errors.title = "タイトルを入力してください";
  else if (countChars(title) > TITLE_MAX) errors.title = `タイトルは${TITLE_MAX}文字以内で入力してください`;
  if (countChars(author) > AUTHOR_MAX) errors.author = `著者は${AUTHOR_MAX}文字以内で入力してください`;
  return errors;
}

export function bookFormErrorsFromServer(error: ApiError): BookFormErrors | null {
  if (error.code !== "VALIDATION_ERROR") return null;
  const errors: BookFormErrors = {};
  for (const f of error.fields) {
    if (f.field === "title") {
      errors.title = f.reason === "required" ? "タイトルを入力してください" : `タイトルは${TITLE_MAX}文字以内で入力してください`;
    }
    if (f.field === "author") errors.author = `著者は${AUTHOR_MAX}文字以内で入力してください`;
  }
  return errors;
}

