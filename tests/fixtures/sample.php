<?php
namespace App\Service;

use App\Repository\UserRepository;
use Exception;

class UserService {
    private UserRepository $repository;

    public function __construct(UserRepository $repository) {
        $this->repository = $repository;
    }

    public function getUser(string $id): array {
        return $this->repository->findById($id);
    }

    private function formatUser(array $data): string {
        return json_encode($data);
    }
}

function topLevelHelper(string $input): string {
    return trim($input);
}
