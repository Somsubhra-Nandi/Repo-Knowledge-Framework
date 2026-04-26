package main

import (
    "fmt"
    "strings"
)

type UserService struct {
    name string
}

type Processor interface {
    Process(input string) string
}

func NewUserService(name string) *UserService {
    return &UserService{name: name}
}

func (s *UserService) GetUser(id string) string {
    return s.formatUser(id)
}

func (s *UserService) formatUser(id string) string {
    return fmt.Sprintf("%s:%s", s.name, id)
}

func TopLevelHelper(text string) string {
    return strings.TrimSpace(text)
}

func main() {
    svc := NewUserService("test")
    result := svc.GetUser("123")
    fmt.Println(TopLevelHelper(result))
}
