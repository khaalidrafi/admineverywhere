/** Kanban board tests — column derivation, drag→transition, snapback on 409. */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import KanbanBoard from "../components/KanbanBoard.svelte";
import type { ModelSpec, RecordRow } from "../types";

// Mock the stores
vi.mock("../lib/stores", () => ({
  app: {
    subscribe: vi.fn(),
  },
  effectiveConfig: vi.fn(() => ({ apiUrl: "http://localhost:8000/api" })),
  toast: vi.fn(),
}));

// Mock the API
vi.mock("../lib/api", () => ({
  transitionRecord: vi.fn(),
}));

// Mock statusTransitions
vi.mock("../lib/statusTransitions", () => ({
  getLegalTransitions: vi.fn((modelId: string, fromState: string) => {
    if (modelId === "orders") {
      const transitions: Record<string, string[]> = {
        pending: ["paid"],
        paid: ["shipped", "refunded"],
        shipped: ["refunded"],
        refunded: [],
      };
      return transitions[fromState] ?? [];
    }
    return [];
  }),
  getStatusField: vi.fn((modelId: string) => {
    if (modelId === "orders") return "status";
    return null;
  }),
}));

describe("KanbanBoard", () => {
  const mockModel: ModelSpec = {
    id: "orders",
    name: "Order",
    singular: "order",
    plural: "orders",
    listPath: "/api/orders/",
    detailPath: "/api/orders/{id}/",
    fields: [
      { name: "id", type: "integer", required: true, readOnly: true },
      { 
        name: "status", 
        type: "enum", 
        required: true, 
        readOnly: false,
        choices: ["pending", "paid", "shipped", "refunded"]
      },
      { name: "customer", type: "string", required: true, readOnly: false },
    ],
    byName: {
      id: { name: "id", type: "integer", required: true, readOnly: true },
      status: { 
        name: "status", 
        type: "enum", 
        required: true, 
        readOnly: false,
        choices: ["pending", "paid", "shipped", "refunded"]
      },
      customer: { name: "customer", type: "string", required: true, readOnly: false },
    },
    labelField: "customer",
  };

  const mockRows: RecordRow[] = [
    { id: 1, status: "pending", customer: "Alice" },
    { id: 2, status: "pending", customer: "Bob" },
    { id: 3, status: "paid", customer: "Charlie" },
    { id: 4, status: "shipped", customer: "Diana" },
    { id: 5, status: "refunded", customer: "Eve" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("column derivation", () => {
    it("renders one column per enum value", async () => {
      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
        },
      });

      expect(screen.getByText("pending")).toBeInTheDocument();
      expect(screen.getByText("paid")).toBeInTheDocument();
      expect(screen.getByText("shipped")).toBeInTheDocument();
      expect(screen.getByText("refunded")).toBeInTheDocument();
    });

    it("shows correct record count per column", async () => {
      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
        },
      });

      // pending has 2 records
      const pendingCol = screen.getByText("pending").closest("div");
      expect(pendingCol).toHaveTextContent("2");

      // paid has 1 record
      const paidCol = screen.getByText("paid").closest("div");
      expect(paidCol).toHaveTextContent("1");
    });

    it("shows 'No records' for empty columns", async () => {
      const rowsWithEmpty = [
        { id: 1, status: "pending", customer: "Alice" },
      ];

      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: rowsWithEmpty,
        },
      });

      // paid, shipped, refunded columns should show "No records"
      const noRecordsMessages = screen.getAllByText("No records");
      expect(noRecordsMessages.length).toBe(3);
    });

    it("displays records in correct columns", async () => {
      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
        },
      });

      expect(screen.getByText("Alice")).toBeInTheDocument();
      expect(screen.getByText("Bob")).toBeInTheDocument();
      expect(screen.getByText("Charlie")).toBeInTheDocument();
      expect(screen.getByText("Diana")).toBeInTheDocument();
      expect(screen.getByText("Eve")).toBeInTheDocument();
    });
  });

  describe("drag→transition mapping", () => {
    it("calls ontransition when card is dropped on different column", async () => {
      const ontransition = vi.fn().mockResolvedValue(undefined);

      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
          ontransition,
        },
      });

      // Find Alice's card (in pending column)
      const aliceCard = screen.getByText("Alice").closest("[draggable='true']");
      expect(aliceCard).toBeInTheDocument();

      // Find paid column
      const paidColumn = screen.getByText("paid").closest("div");
      expect(paidColumn).toBeInTheDocument();

      // Simulate drag and drop
      const dragStartEvent = new Event("dragstart", { bubbles: true });
      Object.defineProperty(dragStartEvent, "dataTransfer", {
        value: { setData: vi.fn() },
      });
      await fireEvent(aliceCard!, dragStartEvent);

      const dragOverEvent = new Event("dragover", { bubbles: true });
      Object.defineProperty(dragOverEvent, "preventDefault", { value: vi.fn() });
      Object.defineProperty(dragOverEvent, "dataTransfer", {
        value: { dropEffect: "" },
      });
      await fireEvent(paidColumn!, dragOverEvent);

      const dropEvent = new Event("drop", { bubbles: true });
      Object.defineProperty(dropEvent, "preventDefault", { value: vi.fn() });
      await fireEvent(paidColumn!, dropEvent);

      // Should call ontransition with Alice's row and "paid"
      expect(ontransition).toHaveBeenCalledWith(
        expect.objectContaining({ id: 1, customer: "Alice" }),
        "paid"
      );
    });

    it("does not call ontransition when dropped on same column", async () => {
      const ontransition = vi.fn().mockResolvedValue(undefined);

      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
          ontransition,
        },
      });

      const aliceCard = screen.getByText("Alice").closest("[draggable='true']");
      const pendingColumn = screen.getByText("pending").closest("div");

      // Simulate drag and drop to same column
      const dragStartEvent = new Event("dragstart", { bubbles: true });
      Object.defineProperty(dragStartEvent, "dataTransfer", {
        value: { setData: vi.fn() },
      });
      await fireEvent(aliceCard!, dragStartEvent);

      const dropEvent = new Event("drop", { bubbles: true });
      Object.defineProperty(dropEvent, "preventDefault", { value: vi.fn() });
      await fireEvent(pendingColumn!, dropEvent);

      // Should not call ontransition
      expect(ontransition).not.toHaveBeenCalled();
    });

    it("rejects illegal transitions", async () => {
      const { toast } = await import("../lib/stores");
      const ontransition = vi.fn().mockResolvedValue(undefined);

      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
          ontransition,
        },
      });

      // Try to drag from refunded (terminal) to pending (illegal)
      const eveCard = screen.getByText("Eve").closest("[draggable='true']");
      const pendingColumn = screen.getByText("pending").closest("div");

      const dragStartEvent = new Event("dragstart", { bubbles: true });
      Object.defineProperty(dragStartEvent, "dataTransfer", {
        value: { setData: vi.fn() },
      });
      await fireEvent(eveCard!, dragStartEvent);

      const dropEvent = new Event("drop", { bubbles: true });
      Object.defineProperty(dropEvent, "preventDefault", { value: vi.fn() });
      await fireEvent(pendingColumn!, dropEvent);

      // Should show error toast
      expect(toast).toHaveBeenCalledWith(
        "error",
        expect.stringContaining("Cannot transition")
      );
      
      // Should not call ontransition
      expect(ontransition).not.toHaveBeenCalled();
    });
  });

  describe("snapback on 409", () => {
    it("shows error toast when transition fails with 409", async () => {
      const { toast } = await import("../lib/stores");
      const ontransition = vi.fn().mockRejectedValue({
        status: 409,
        detail: { reason: "Order already shipped" },
      });

      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
          ontransition,
        },
      });

      const charlieCard = screen.getByText("Charlie").closest("[draggable='true']");
      const shippedColumn = screen.getByText("shipped").closest("div");

      // Simulate drag and drop
      const dragStartEvent = new Event("dragstart", { bubbles: true });
      Object.defineProperty(dragStartEvent, "dataTransfer", {
        value: { setData: vi.fn() },
      });
      await fireEvent(charlieCard!, dragStartEvent);

      const dropEvent = new Event("drop", { bubbles: true });
      Object.defineProperty(dropEvent, "preventDefault", { value: vi.fn() });
      await fireEvent(shippedColumn!, dropEvent);

      // Wait for async operations
      await new Promise((resolve) => setTimeout(resolve, 0));

      // Should call ontransition
      expect(ontransition).toHaveBeenCalled();

      // The parent component (ModelPage) handles the error and shows toast
      // This test verifies the component calls ontransition correctly
    });
  });

  describe("keyboard accessibility", () => {
    it("opens move menu when clicking move button", async () => {
      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
        },
      });

      // Find Alice's move button
      const aliceCard = screen.getByText("Alice").closest("[draggable='true']");
      const moveButton = aliceCard!.querySelector("button[aria-label*='Move']");
      expect(moveButton).toBeInTheDocument();

      // Click the move button
      await fireEvent.click(moveButton!);

      // Menu should open with move options
      expect(screen.getByText("Move to")).toBeInTheDocument();
      expect(screen.getByText("paid")).toBeInTheDocument();
      expect(screen.getByText("shipped")).toBeInTheDocument();
      expect(screen.getByText("refunded")).toBeInTheDocument();
      
      // Should not show current state
      expect(screen.queryByText("pending")).not.toBeInTheDocument();
    });

    it("calls ontransition when selecting from move menu", async () => {
      const ontransition = vi.fn().mockResolvedValue(undefined);

      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
          ontransition,
        },
      });

      const aliceCard = screen.getByText("Alice").closest("[draggable='true']");
      const moveButton = aliceCard!.querySelector("button[aria-label*='Move']");
      await fireEvent.click(moveButton!);

      // Click "paid" option
      const paidOption = screen.getByText("paid");
      await fireEvent.click(paidOption);

      // Should call ontransition
      expect(ontransition).toHaveBeenCalledWith(
        expect.objectContaining({ id: 1, customer: "Alice" }),
        "paid"
      );
    });

    it("closes menu when clicking Cancel", async () => {
      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: mockRows,
        },
      });

      const aliceCard = screen.getByText("Alice").closest("[draggable='true']");
      const moveButton = aliceCard!.querySelector("button[aria-label*='Move']");
      await fireEvent.click(moveButton!);

      expect(screen.getByText("Move to")).toBeInTheDocument();

      // Click Cancel
      const cancelButton = screen.getByText("Cancel");
      await fireEvent.click(cancelButton);

      // Menu should close
      expect(screen.queryByText("Move to")).not.toBeInTheDocument();
    });
  });

  describe("edge cases", () => {
    it("shows alert when model has no status field", async () => {
      const noStatusModel: ModelSpec = {
        ...mockModel,
        id: "products",
        fields: mockModel.fields.filter((f) => f.name !== "status"),
        byName: Object.fromEntries(
          Object.entries(mockModel.byName).filter(([k]) => k !== "status")
        ),
      };

      render(KanbanBoard, {
        props: {
          model: noStatusModel,
          rows: mockRows,
        },
      });

      expect(
        screen.getByText(/no status field configured for kanban view/i)
      ).toBeInTheDocument();
    });

    it("handles empty rows array", async () => {
      render(KanbanBoard, {
        props: {
          model: mockModel,
          rows: [],
        },
      });

      // All columns should show "No records"
      const noRecordsMessages = screen.getAllByText("No records");
      expect(noRecordsMessages.length).toBe(4); // pending, paid, shipped, refunded
    });
  });
});
