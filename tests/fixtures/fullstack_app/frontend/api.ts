export async function fetchUser(id: string): Promise<Response> {
    return fetch(`/api/users/${id}`);
}


export async function fetchAllUsers(): Promise<Response> {
    return fetch("/api/users");
}
