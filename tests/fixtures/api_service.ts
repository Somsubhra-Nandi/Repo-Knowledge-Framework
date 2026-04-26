const BASE_URL = "/api";

export async function getUsers(): Promise<Response> {
    return fetch(`${BASE_URL}/users`);
}

export async function getUserById(id: string): Promise<Response> {
    return fetch(`/api/users/${id}`);
}

export async function createUser(data: object): Promise<Response> {
    return fetch("/api/users", {
        method: "POST",
        body: JSON.stringify(data),
    });
}

export async function deleteUser(id: string): Promise<Response> {
    return fetch(`/api/users/${id}`, { method: "DELETE" });
}

export async function updateUser(id: string, data: object): Promise<Response> {
    return fetch(`/api/users/${id}`, { method: "PUT" });
}
