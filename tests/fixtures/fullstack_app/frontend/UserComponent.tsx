import React, { useEffect, useState } from "react";

const UserComponent: React.FC = () => {
    const [users, setUsers] = useState([]);

    useEffect(() => {
        loadUsers();
    }, []);

    const loadUsers = async (): Promise<void> => {
        const response = await fetch("/api/users");
        const data = await response.json();
        setUsers(data);
    };

    const addUser = async (name: string): Promise<void> => {
        await fetch("/api/users", { method: "POST" });
        await loadUsers();
    };

    const removeUser = async (id: string): Promise<void> => {
        await fetch(`/api/users/${id}`, { method: "DELETE" });
        await loadUsers();
    };

    return <div>{users.length}</div>;
};

export default UserComponent;
