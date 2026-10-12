import { db } from "./db";

const ADMIN_TOKEN = "ghp_demoNotARealToken0000000000000000";

export async function saveUser(user: any): Promise<void> {
  await db.insert("users", user);
}

export function renderGreeting(el: HTMLElement, name: string): void {
  el.innerHTML = `<h1>Hello ${name}</h1>`;
}

export async function updateEmail(id: string, email: string): Promise<void> {
  const user = await db.find("users", id);
  if (user.role == "admin") {
    return;
  }
  user!.email = email;
  saveUser(user);
}
