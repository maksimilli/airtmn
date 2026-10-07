import { useEffect, useState } from "react";
import { request } from "./model";
const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
type User = {
  id: number;
  username: string;
  role: "viewer" | "admin";
  enabled: boolean;
};

export function LoginPanel({ onDone }: { onDone: () => Promise<void> }) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <section className="panel login-panel">
      <h2>Вход администратора</h2>
      <p>Для просмотра каталога вход не требуется.</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            await request("/api/auth/login", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ username, password }),
            });
            setPassword("");
            await onDone();
          } catch (e) {
            setError(errorText(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Логин
          <input
            autoComplete="username"
            required
            maxLength={40}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label>
          Пароль
          <input
            type="password"
            autoComplete="current-password"
            required
            maxLength={200}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
        <button className="button primary" disabled={busy}>
          {busy ? "Вход…" : "Войти"}
        </button>
      </form>
    </section>
  );
}
function UserRow({
  user,
  reload,
}: {
  user: User;
  reload: () => Promise<void>;
}) {
  const [role, setRole] = useState(user.role),
    [enabled, setEnabled] = useState(Boolean(user.enabled));
  const [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    setRole(user.role);
    setEnabled(Boolean(user.enabled));
  }, [user.role, user.enabled]);
  return (
    <tr>
      <td>{user.username}</td>
      <td>
        <select
          aria-label={"Права " + user.username}
          value={role}
          onChange={(e) => setRole(e.target.value as User["role"])}
        >
          <option value="admin">Администратор</option>
          <option value="viewer">Только просмотр</option>
        </select>
      </td>
      <td>
        <label className="user-enabled">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            aria-label={"Доступ " + user.username}
          />
          Доступ включён
        </label>
      </td>
      <td>
        <input
          aria-label={"Новый пароль " + user.username}
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={200}
          placeholder="Оставьте пустым"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </td>
      <td>
        <button
          className="button secondary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              if (password && password.length < 12)
                throw new Error("Пароль должен содержать не менее 12 символов");
              await request("/api/users/" + user.id, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  role,
                  enabled,
                  ...(password ? { password } : {}),
                }),
              });
              setPassword("");
              await reload();
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          Сохранить
        </button>
        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}
      </td>
    </tr>
  );
}
export function UsersPanel() {
  const [users, setUsers] = useState<User[]>([]),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  async function reload() {
    setUsers(await request("/api/users"));
  }
  useEffect(() => {
    void reload().catch((e) => setError(errorText(e)));
  }, []);
  return (
    <>
      <section className="panel users-create">
        <h2>Добавить администратора</h2>
        <p>Администратор сможет изменять каталог и управлять доступом.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            setNotice("");
            try {
              await request("/api/users", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password, role: "admin" }),
              });
              setUsername("");
              setPassword("");
              setNotice(
                "Учётная запись создана. Передайте логин и пароль новому администратору.",
              );
              await reload();
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Новый логин
            <input
              required
              minLength={3}
              maxLength={40}
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label>
            Пароль нового пользователя
            <input
              type="password"
              required
              minLength={12}
              maxLength={200}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button className="button primary" disabled={busy}>
            Создать
          </button>
        </form>
        {error && (
          <p role="alert" className="auth-error">
            {error}
          </p>
        )}
        {notice && <p role="status">{notice}</p>}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Учётные записи</h2>
        </div>
        <div className="table-wrap">
          <table className="users-table">
            <thead>
              <tr>
                <th>Логин</th>
                <th>Права</th>
                <th>Доступ</th>
                <th>Сменить пароль</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <UserRow key={u.id} user={u} reload={reload} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
