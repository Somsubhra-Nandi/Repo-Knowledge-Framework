import React, { useEffect, useState } from "react";
import axios from "axios";

interface User {
    id: string;
    name: string;
}

const UserList: React.FC = () => {
    const [users, setUsers] = useState<User[]>([]);

    useEffect(() => {
        fetchUsers();
    }, []);

    const fetchUsers = async (): Promise<void> => {
        const response = await fetch("/api/users");
        const data = await response.json();
        setUsers(data);
    };

    const createUser = async (name: string): Promise<void> => {
        await axios.post("/api/users", { name });
        await fetchUsers();
    };

    const deleteUser = async (id: string): Promise<void> => {
        await fetch(`/api/users/${id}`, { method: "DELETE" });
        await fetchUsers();
    };

    const updateUser = async (id: string, name: string): Promise<void> => {
        await axios.put(`/api/users/${id}`, { name });
    };

    return <div>{users.length}</div>;
};

export default UserList;
