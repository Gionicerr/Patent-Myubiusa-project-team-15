export interface Note {
  id: string;
  ownerId: string;
  title: string;
  text: string;
  createdAt: string;
}
export interface CreateNoteRequest { title: string; text?: string; }
export interface ApiProblem { code: string; message: string; }
