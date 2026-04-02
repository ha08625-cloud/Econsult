# Public slug column
Before we dive into the code changes, there is an important architectural constraint to highlight based on your current setup. The system is strictly designed as a single-tenant deployment. Currently, `PRACTICE_ID` is enforced via an environment variable, and the application will abort on startup if the database contains more than one practice. 

Since public slugs are traditionally used for multi-tenant routing (e.g., routing a patient to `/{public_slug}/conditions`), introducing one to a strictly single-tenant app means we need to decide if this slug is just cosmetic data for the frontend, or the first step toward multi-tenancy.

Keeping that in mind, here is a straightforward, end-to-end plan to safely introduce the `public_slug` column to your current architecture:

### 1. Database Migration (Alembic)
You will need a new Alembic migration to modify the schema. Since your last migration was `0005` (removing the default timestamp on submissions), this will be revision `0006`.
* **Action**: Generate a new Alembic script in `alembic/versions/`.
* **SQL**: Execute an `ALTER TABLE practices ADD COLUMN public_slug VARCHAR(255) UNIQUE;` command.
* **Constraint**: You may want to allow `NULL` initially or backfill existing records to prevent the migration from failing on populated databases.

### 2. Practice Repository Updates
The `PracticeRepository` handles all database interactions for the `practices` table.
* **Update `create_practice`**: Modify the `INSERT` statement to accept and write the `public_slug`.
* **Update `get_practice`**: Include `public_slug` in the `SELECT` statement so it is returned in the dictionary.
* **Add `update_slug`**: Create a new method (similar to `update_email`) to allow the admin to change their slug safely, ensuring you catch potential `UniqueViolation` errors if you ever move to multi-tenant.

### 3. Startup Validation Seed
When the server starts empty, it seeds the practice record.
* **Update `_validate_startup`**: Pass a default `public_slug` (perhaps derived from the `PRACTICE_NAME` or just a hardcoded default like `"demo-practice"`) into the `practice_repo.create_practice` call.

### 4. Admin API Exposure
The admin portal needs to be able to read and edit this new value.
* **Update `GET /admin/practice`**: Ensure `public_slug` is included in the returned JSON object.
* **Create `PUT /admin/practice/slug`**: Add a new endpoint to accept a JSON body like `{"public_slug": "my-new-slug"}`, validate the string (e.g., alphanumeric and hyphens only), and call the new repository method.

### 5. Frontend & Public API Consideration
Right now, the public API (`public_router.py`) relies entirely on the `practice_id` injected from the application state.
* **Action**: If the frontend needs to know its slug (perhaps for display or building links), you will want to update `GET /practice` in `public_router.py` to return the `public_slug` alongside the `practice_name`.

---

To help me tailor the next steps, how do you plan to use this `public_slug`—is it strictly for cosmetic URL formatting within your single-tenant frontend, or are you planning to transition the core engine to support multiple practices per database?
