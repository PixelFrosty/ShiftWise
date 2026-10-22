import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';

import { EmployeeDeleteConfirmComponent } from './employee-delete-confirm.component';

describe('EmployeeDeleteConfirmComponent', () => {
  let component: EmployeeDeleteConfirmComponent;
  let fixture: ComponentFixture<EmployeeDeleteConfirmComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EmployeeDeleteConfirmComponent],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => '1' } } }
        }
      ]
    })
    .compileComponents();

    fixture = TestBed.createComponent(EmployeeDeleteConfirmComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
