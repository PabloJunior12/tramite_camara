from rest_framework import routers
from django.urls import path
from .views import CompanyViewSet, ProcedureViewSet, SubjectViewSet, FinancePaymentsExcelAPIView, FinanceAPIView, SpecialtyViewSet, UpdateCasePartyView, DeleteCasePartyView, AccountingDashboardView, PaymentsReportPDFView, ProceduralStageViewSet, CaseLocationViewSet, ArbitrationCaseViewSet, CreateCasePartyView, ArbitrationCaseFileViewSet, ArbitrationCaseMeetingViewSet, ArbitrationCaseObservationViewSet, ArbitrationCaseNotificationViewSet, CasePartyLawyerListCreateAPIView, CaseBudgetAPIView, CasePaymentListCreateAPIView, CasePaymentVoidAPIView

router = routers.DefaultRouter()
router.register("company", CompanyViewSet)
router.register("tramites", ProcedureViewSet, basename="tramite")
router.register("expedientes", ArbitrationCaseViewSet, basename="expediente")
router.register("specialty", SpecialtyViewSet, basename="specialty")
router.register("subject", SubjectViewSet, basename="subject")
router.register("procedural-stages", ProceduralStageViewSet, basename="procedural-stage")
router.register("case-locations", CaseLocationViewSet, basename="case-location")

case_file_list = ArbitrationCaseFileViewSet.as_view({
    "get": "list",
    "post": "create",
})

meeting_list = ArbitrationCaseMeetingViewSet.as_view({
    "get": "list",
    "post": "create",
})

observation_list = ArbitrationCaseObservationViewSet.as_view({
    "get": "list",
    "post": "create",
})

notification_list = ArbitrationCaseNotificationViewSet.as_view({
    "get": "list",
    "post": "create",
})

urlpatterns = [

    path("dashboard/contabilidad/", AccountingDashboardView.as_view()),
    
    path("cases/<int:case_pk>/files/", case_file_list, name="arbitration-case-files"),
    path("cases/<int:case_pk>/meetings/",meeting_list, name="arbitration-case-meetings"),
    path("cases/<int:case_pk>/observations/", observation_list, name="arbitration-case-observations"),
    path("cases/<int:case_pk>/notifications/", notification_list, name="arbitration-case-notifications"),

    path("case-parties/<int:case_party_id>/lawyers/",CasePartyLawyerListCreateAPIView.as_view(),name="case-party-lawyers"),
    path("case-parties/<int:case_party_id>/lawyers/<int:assignment_id>/", CasePartyLawyerListCreateAPIView.as_view(), name="case-party-lawyer-detail"),
  
    path("cases/<int:case_id>/budget/",CaseBudgetAPIView.as_view(),name="case-budget"),
    path("cases/<int:case_id>/payments/",CasePaymentListCreateAPIView.as_view(),name="case-payments"),
    path("cases/<int:case_id>/payments/<int:payment_id>/void/", CasePaymentVoidAPIView.as_view(), name="case-payment-void"),

    path("reports/payments/pdf/", PaymentsReportPDFView.as_view(), name="payments-report-pdf"),

    # PARTES

    path("cases/<int:case_id>/parties/create-user/", CreateCasePartyView.as_view(), name="case-party-create-user"),
    path("cases/<int:case_id>/parties/<int:case_party_id>/", UpdateCasePartyView.as_view(), name="case-party-detail"),
    path("cases/<int:case_id>/parties/<int:case_party_id>/delete/", DeleteCasePartyView.as_view(), name="case-party-delete"),

    path("finanzas/", FinanceAPIView.as_view(), name="finanzas"),
    path("finanzas/reporte-excel/", FinancePaymentsExcelAPIView.as_view(), name="finanzas-reporte-excel"),


] + router.urls
